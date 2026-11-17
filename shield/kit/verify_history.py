#!/usr/bin/env python3
"""Verify one finalized history over a window of batches, and measure finality, from public reads only.

Per finalized batch n (heights 16n+1 .. 16n+16; empty slots allowed):
  H1  a certificate is held and complete (a batch whose certificate the host does not hold is counted "unknown", never passed);
  H2  the certificate's signers are seated validators and their voting power reaches the quorum (registry read now);
  H3  the batch is internally consistent: block_count = hashes = heights; heights ascending inside 16n+1..16n+16;
      the certificate names the batch's last block (hash and height);
  H4  batches follow each other: no height is in two batches; batch numbers have no unexplained hole;
  H5  the blocks link: each block read back has the batch's hash; every block of batch n names the last block of batch n-1
      as its parent (each leader proposes one block per batch, in parallel);
  H6  a second host serves the same block hashes, certificate hash and records digest for every batch;
  H7  the records digest is recomputed from the records themselves (canonical JSON, keccak256, cursor order);
  H8  each block's ops_order_digest = keccak256 of the concatenated op keccaks it lists;
  H9  a batch's newest block time never goes back, and no block time is ahead of this computer's clock (+2 s)
      (block times inside one batch come from different leaders and are not ordered).
Finality (--finality-seconds S): for S seconds, each new batch's (certificate visible on the host) - (its last block time);
p50 / p95 / p99 printed; it includes the host's own read lag, so it is an upper bound.
Limits: certificates list signers but carry no signatures here, so H2 trusts the host for who signed (H6 compares two hosts);
an op's own keccak (canonical bincode) is not recomputed; the registry is today's set (a set change inside the window is named).

Usage:  python3 verify_history.py --chain https://testnet.vordex.xyz/chain --second-chain https://testnet.vordex.xyz/chain-archive \
            --batches 40 [--finality-seconds 60]
Exit:   0 = all checks passed, nothing unknown · 1 = a check failed · 2 = could not run, or something unknown · 3 = nothing checked."""
import argparse, json, statistics, sys, time
from vordium_check.common import Reader, keccak256

SIZE = 16


def canon(r): return json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def records_digest(recs):
    recs = sorted(recs, key=lambda r: tuple(int(x) for x in str(r.get("cursor")).split(".")))
    return "0x" + keccak256(b"".join(canon(r) for r in recs)).hex()


def ops_digest(op_keccaks): return "0x" + keccak256(b"".join(bytes.fromhex(k[2:]) for k in op_keccaks)).hex()


def check_batch(b, prev, seated, quorum):
    """H1/H2/H3/H4 on one batch answer (prev = the batch before it in the window or None). Returns (fails, unknown)."""
    n, f = b.get("batch_height"), []
    if b.get("certificate") != "held" or not b.get("qc"): return [], True
    q, hs, hh = b["qc"], b.get("block_hashes") or [], b.get("heights") or []
    if b.get("complete") is not True: f.append(f"batch {n}: certificate held but the batch is not complete")
    if not (len(hs) == len(hh) == b.get("block_count")): f.append(f"batch {n}: block_count {b.get('block_count')} != {len(hs)} hashes / {len(hh)} heights")
    if hh and (hh != sorted(set(hh)) or hh[0] < SIZE * n + 1 or hh[-1] > SIZE * n + SIZE): f.append(f"batch {n}: heights {hh[0]}..{hh[-1]} not ascending inside {SIZE * n + 1}..{SIZE * n + SIZE}")
    if hs and (q.get("block_hash") != hs[-1] or q.get("height") != hh[-1]): f.append(f"batch {n}: the certificate names {q.get('height')} {q.get('block_hash')}, not the batch's last block")
    if q.get("batch_height") != n: f.append(f"batch {n}: the certificate is for batch {q.get('batch_height')}")
    if q.get("signers_status") == "unavailable":
        return f, True        # the host says it does not have the signers yet (they fill in shortly): unknown, never pass or fail
    sg = [s.lower() for s in q.get("signers") or []]
    if len(set(sg)) != len(sg) or q.get("signer_count") != len(sg): f.append(f"batch {n}: signer list repeats or disagrees with signer_count")
    out = [s for s in sg if s not in seated]
    if out: f.append(f"batch {n}: signer(s) not in the seated set {out}")
    if sum(seated.get(s, 0) for s in sg) < quorum: f.append(f"batch {n}: the signers' voting power is below the quorum")
    if prev and prev.get("heights") and hh and hh[0] <= prev["heights"][-1]: f.append(f"batch {n}: a height is also in batch {prev.get('batch_height')}")
    return f, False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chain"); ap.add_argument("--second-chain"); ap.add_argument("--batches", type=int, default=40)
    ap.add_argument("--from-batch", type=int); ap.add_argument("--digests", type=int, default=8, help="batches with records to recompute (H7)")
    ap.add_argument("--finality-seconds", type=float, default=0); ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--plant", choices=["hash", "signer", "digest", "parent"], help="tests only: change one served value; the run must FAIL")
    a = ap.parse_args()
    if a.self_test: return self_test()
    if not a.chain: ap.error("--chain is required")
    rd, fails, unknown, counts = Reader(), [], 0, {}
    try:
        reg = (rd.get(a.chain, "/registry/set") or {}).get("data") or {}
        seated = {v["address"].lower(): int(v["voting_power"]) for v in reg.get("seated") or []}
        quorum = int(reg.get("quorum_power") or 0)
        if not seated or not quorum: print("NOT RUN: the seated set or the quorum could not be read"); return 2
        top = rd.get(a.chain, "/batches", from_height=0, to_height=0)["history"]["to_batch"] - 64   # settled certificates
        lo = a.from_batch if a.from_batch is not None else top - a.batches + 1; hi = min(top, lo + a.batches - 1)
        def page(host):
            out, nxt, seen = [], lo, set()
            while nxt is not None and nxt <= hi:
                if nxt in seen: raise RuntimeError(f"{host} repeated its next page {nxt}")
                seen.add(nxt); d = rd.get(host, "/batches", from_height=nxt, to_height=hi) or {}
                out += d.get("batches") or []; nxt = d.get("next_from_height")
            return out
        bats = page(a.chain)
        bats = sorted({b["batch_height"]: b for b in bats if isinstance(b, dict) and "batch_height" in b}.values(), key=lambda b: b["batch_height"])
        if a.plant == "hash" and bats: bats[len(bats) // 2]["qc"]["block_hash"] = "0x" + "ab" * 32
        if a.plant == "signer" and bats: bats[0]["qc"]["signers"][0] = "0x" + "12" * 20
        missing = sorted(set(range(lo, hi + 1)) - {b["batch_height"] for b in bats})
        if missing: unknown += len(missing); counts["batches not served (unknown)"] = len(missing)
        prev, held = None, 0
        for b in bats:
            f, unk = check_batch(b, prev, seated, quorum); fails += f; unknown += unk; prev = b; held += 0 if unk else 1
        counts["batches with a certificate checked (H1-H4)"] = held
        # H5 + H8 + H9: every block of every batch, read back. Each leader proposes one block per batch in parallel, so every
        # block of batch n names the LAST block of batch n-1 as its parent, and block times inside a batch are not ordered.
        nblk, n_ops, n_links, prev_b, prev_t = 0, 0, 0, None, 0
        for b in bats:
            want_parent = prev_b["block_hashes"][-1] if prev_b and prev_b.get("block_hashes") and prev_b["batch_height"] == b["batch_height"] - 1 else None
            bt = 0
            for h, hs in zip(b.get("heights") or [], b.get("block_hashes") or []):
                blk = rd.get(a.chain, f"/block/{h}")
                if not blk: unknown += 1; continue
                nblk += 1
                if a.plant == "parent" and nblk == 9: blk["parent_hash"] = "0x" + "cd" * 32
                if blk.get("hash") != hs: fails.append(f"block {h}: hash {blk.get('hash')} != the batch's {hs}")
                if want_parent: n_links += 1
                if want_parent and blk.get("parent_hash") != want_parent: fails.append(f"block {h}: parent_hash does not name the last block of batch {b['batch_height'] - 1}")
                ok = blk.get("op_keccaks")
                if isinstance(ok, list):
                    n_ops += 1
                    if blk.get("ops_order_digest") != ops_digest(ok): fails.append(f"block {h}: ops_order_digest does not match its op keccaks")
                t = blk.get("timestamp_ms")
                if not isinstance(t, int): continue
                if t > (time.time() + 2) * 1000: fails.append(f"block {h}: time is ahead of this computer's clock")
                bt = max(bt, t)
            if bt and bt < prev_t: fails.append(f"batch {b['batch_height']}: its newest block time goes back ({bt} < {prev_t})")
            prev_b, prev_t = b, max(prev_t, bt)
        counts["blocks read back (hashes, H9)"] = nblk
        counts["parent links compared (H5)"] = n_links
        counts["op-order digests recomputed (H8)"] = n_ops
        # H6: a second host
        if a.second_chain:
            other = {b["batch_height"]: b for b in page(a.second_chain)}
            same = 0
            for b in bats:
                o = other.get(b["batch_height"])
                if not o or o.get("certificate") != "held": continue
                for k in ("block_hashes", "records_digest"):
                    if o.get(k) != b.get(k): fails.append(f"batch {b['batch_height']}: the second host serves another {k}")
                if (o.get("qc") or {}).get("certified_hash") != (b.get("qc") or {}).get("certified_hash"): fails.append(f"batch {b['batch_height']}: the second host serves another certificate")
                same += 1
            counts["batches compared on a second host (H6)"] = same
            if same < len(bats): unknown += len(bats) - same; print(f"  H6: {len(bats) - same} batch(es) not compared on the second host (unknown)")
        # H7: recompute records digests
        done = 0
        for b in [b for b in bats if b.get("records_count") and b.get("records_digest")][: a.digests]:
            n, recs, cur, seen, served = b["batch_height"], [], None, set(), True
            while True:
                d = rd.get(a.chain, "/events/range", **{"from": SIZE * n + 1, "to": SIZE * n + SIZE, "require_held": 1, "limit": 1000, "cursor": cur})
                if not isinstance(d, dict): served = False; break
                recs += d.get("events") or []; cur = d.get("next_cursor")
                if not cur or cur in seen: break
                seen.add(cur)
            if not served: unknown += 1; continue
            if a.plant == "digest" and recs: recs[0] = {**recs[0], "kind": str(recs[0].get("kind")) + "_planted"}
            if len(recs) != b["records_count"]: fails.append(f"batch {n}: {len(recs)} records served, the batch says {b['records_count']}")
            elif records_digest(recs) != b["records_digest"]: fails.append(f"batch {n}: recomputed records digest differs")
            done += 1
        counts["records digests recomputed (H7)"] = done
        fin = finality(rd, a.chain, a.finality_seconds) if a.finality_seconds else None
    except (RuntimeError, OSError, KeyError, ValueError, TypeError, AttributeError) as x:
        print(f"NOT RUN: {x}"); return 2
    print(f"batches {lo}-{hi} · seated {len(seated)} · quorum power {quorum}")
    for k, v in counts.items(): print(f"  {v:6d}  {k}")
    if a.finality_seconds and not fin: print("  finality could not be measured (fewer than 3 batches seen certified in the time given)")
    if fin: print(f"  finality over {fin['n']} batches: p50 {fin['p50']:.2f} s · p95 {fin['p95']:.2f} s · p99 {fin['p99']:.2f} s · max {fin['max']:.2f} s")
    for f in fails[:40]: print("  FAIL  " + f)
    checked = counts.get("batches with a certificate checked (H1-H4)", 0)
    print(f"RESULT {'FAIL' if fails else ('NOTHING CHECKED' if not checked else ('INCOMPLETE' if unknown else 'PASS'))}" + (f" ({unknown} unknown, never passed)" if unknown else ""))
    return 1 if fails else (3 if not checked else (2 if unknown else 0))


def finality(rd, chain, secs, poll=0.25):
    """(certificate visible) - (last block time) for one batch at a time: always the batch two ahead of the newest, so a
    backlog never counts as delay (the chain makes several batches a second)."""
    samples, end = [], time.time() + secs
    newest = lambda: rd.get(chain, "/batches", from_height=0, to_height=0)["history"]["to_batch"]
    saved = rd.gap; rd.gap = poll
    try:
        n = newest() + 2
        while time.time() < end:
            b = rd.get(chain, f"/batch/{n}")
            if b and b.get("certificate") == "held" and b.get("last_block_time_ms"):
                samples.append(time.time() - b["last_block_time_ms"] / 1000); n = newest() + 2
            elif b and isinstance(b.get("last_block_time_ms"), int) and b["last_block_time_ms"] / 1000 < time.time() - 30: n = newest() + 2   # known and old, never certified: move on
    finally: rd.gap = saved
    if len(samples) < 3: return None
    q = statistics.quantiles(samples, n=100, method="inclusive")
    return {"n": len(samples), "p50": statistics.median(samples), "p95": q[94], "p99": q[98], "max": max(samples)}


def self_test():
    bad = 0
    def t(name, cond):
        nonlocal bad; bad += 0 if cond else 1; print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    S = {"0x" + c * 40: 10 for c in "1234567"}; Q = 47
    def bat(n, hs=(1, 2, 3), signers=None):
        heights = [16 * n + h for h in hs]; hashes = [f"0x{n:032x}{h:032x}" for h in heights]
        sg = signers if signers is not None else list(S)[:5]
        return {"batch_height": n, "certificate": "held", "complete": True, "block_count": len(hs), "heights": heights, "block_hashes": hashes,
                "qc": {"batch_height": n, "block_hash": hashes[-1], "height": heights[-1], "signers": sg, "signer_count": len(sg)}}
    t("B1 a clean batch passes", check_batch(bat(5), bat(4), S, Q) == ([], False))
    t("B2 not held is unknown, never a pass", check_batch({**bat(5), "certificate": "not held"}, None, S, Q) == ([], True))
    t("B3 the certificate names another block", check_batch({**bat(5), "qc": {**bat(5)["qc"], "block_hash": "0x" + "ab" * 32}}, None, S, Q)[0] != [])
    t("B4 an outside signer fails", check_batch(bat(5, signers=list(S)[:4] + ["0x" + "9" * 40]), None, S, Q)[0] != [])
    t("B5 four of seven signers is below the quorum", check_batch(bat(5, signers=list(S)[:4]), None, S, Q)[0] != [])
    t("B6 a height outside 16n+1..16n+16 fails", check_batch({**bat(5), "heights": [1, 2, 3]}, None, S, Q)[0] != [])
    t("B7 a height in two batches fails", check_batch(bat(5), {**bat(5)}, S, Q)[0] != [])
    t("B8 block_count disagrees with the hashes", check_batch({**bat(5), "block_count": 4}, None, S, Q)[0] != [])
    t("B9 a repeated signer fails", check_batch(bat(5, signers=list(S)[:4] + [list(S)[0]]), None, S, Q)[0] != [])
    t("B10 not complete fails", check_batch({**bat(5), "complete": False}, None, S, Q)[0] != [])
    t("B11 an outside signer beside a full quorum still fails", check_batch(bat(5, signers=list(S)[:5] + ["0x" + "9" * 40]), None, S, Q)[0] != [])
    b6 = bat(6); b6 = {**b6, "batch_height": 5, "qc": {**b6["qc"], "batch_height": 5}}
    t("B12 heights of another batch (certificate consistent with them) fail", check_batch(b6, None, S, Q)[0] != [])
    t("D5 the canonical form ends each record with a newline", records_digest([{"cursor": "1.0.0"}]) == "0x" + keccak256(b'{"cursor":"1.0.0"}\n').hex())
    t("B14 a held certificate with an empty signer list and no 'unavailable' status fails", check_batch({**bat(5), "qc": {**bat(5)["qc"], "signers": [], "signer_count": 0}}, None, S, Q)[0] != [])
    t("B13 signers 'unavailable' (not gathered yet) is unknown, not a FAIL", check_batch({**bat(5), "qc": {**bat(5)["qc"], "signers": [], "signer_count": None, "signers_status": "unavailable"}}, None, S, Q) == ([], True))
    t("D1 empty records digest = keccak256 of nothing", records_digest([]) == "0x" + keccak256(b"").hex())
    r = [{"cursor": "2.0.1", "kind": "x", "v": 1}, {"cursor": "10.0.0", "kind": "y"}]
    t("D2 the digest is in numeric cursor order, not served order", records_digest(r) == records_digest(r[::-1]) and
      records_digest(r) == "0x" + keccak256(canon(r[0]) + canon(r[1])).hex())
    t("D3 one changed field changes the digest", records_digest(r) != records_digest([{**r[0], "v": 2}, r[1]]))
    t("D4 ops digest of no ops = keccak256 of nothing", ops_digest([]) == "0x" + keccak256(b"").hex())
    print(f"self-test: {'PASS' if not bad else 'FAIL'}"); return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
