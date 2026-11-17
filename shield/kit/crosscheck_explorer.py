#!/usr/bin/env python3
"""Cross-check the explorer's numbers against the chain, from public reads only.

  X1  /truth.json: every fact is re-read at the public source it names; fixed facts (chain id, genesis, release, seated count)
      must be equal; moving facts (head, finalized height, certified batch) may only lag the source by what the stated
      staleness allows, never lead it;
  X2  /api/live-facts: chain id, genesis, trading open, deposits open, EVM live, the validator count, and every protocol
      upgrade's on/off state by name, against the chain's own answers (/status, /truth/v1, /registry/set);
  X3  block hashes: for the newest certified batches, every block hash the explorer serves equals the certificate's;
  X5  freshness: the explorer's newest indexed block is at most --max-lag seconds (default 120) behind the chain's head;
  X4  market rules: the explorer's market specs equal the chain's (pair by pair), read with the held-still rule (a value that
      moved between two chain reads is not compared).
A value the explorer could not serve is UNREAD (counted, never a pass); a value that differs is a FAIL.

Usage:  python3 crosscheck_explorer.py --site https://vordscan.io --chain https://rpc.vordium.com [--batches 4]
        python3 crosscheck_explorer.py --site https://testnet.vordscan.io --chain https://testnet.vordex.xyz/chain --truth-host https://rpc-testnet.vordium.com
Exit:   0 = all values agree, none unread · 1 = a value differs · 2 = could not run, or some value unread · 3 = nothing compared."""
import argparse, sys, time
from vordium_check.common import Reader


def by_name(rules):
    return {r.get("name"): bool(r.get("active")) for r in rules or [] if isinstance(r, dict) and r.get("name")}


def compare_upgrades(feed_acts, truth_rules):
    """[(name, explorer, chain)] for every name both sides list whose on/off differs; plus names only one side lists."""
    f = {a.get("name"): bool(a.get("active")) for a in feed_acts or [] if isinstance(a, dict) and a.get("name")}
    t = by_name(truth_rules)
    diff = [(n, f[n], t[n]) for n in sorted(set(f) & set(t)) if f[n] != t[n]]
    return diff, sorted(set(t) - set(f)), sorted(set(f) - set(t))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site"); ap.add_argument("--chain"); ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--max-lag", type=float, default=120, help="X5: seconds the block index may lag the chain")
    ap.add_argument("--truth-host", help="host that serves /truth/v1 when it is not --chain (test network: https://rpc-testnet.vordium.com)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return self_test()
    if not (a.site and a.chain): ap.error("--site and --chain are required")
    rd, fails, unread, agree = Reader(), [], [], 0
    def ok(cond, text):
        nonlocal agree
        if cond: agree += 1
        else: fails.append(text)
    def sget(path, **kw):
        """an explorer read that fails is UNREAD for its check, never the end of the run"""
        try: return rd.get(a.site, path, **kw)
        except RuntimeError: return None
    def eq(label, site_v, chain_v):
        """a value missing on either side is UNREAD, never agreement"""
        if site_v is None or chain_v is None: unread.append(f"{label} (explorer {site_v!r}, chain {chain_v!r})")
        else: ok(site_v == chain_v, f"{label}: the explorer says {site_v!r}, the chain {chain_v!r}")
    try:
        st, tr = rd.get(a.chain, "/status") or {}, rd.get(a.truth_host or a.chain, "/truth/v1") or {}
        reg = (rd.get(a.chain, "/registry/set") or {}).get("data") or {}
        if not st or not tr: print("NOT RUN: the chain's /status or /truth/v1 did not answer"); return 2
        # X1
        tj = sget("/truth.json")
        if not tj: unread.append("X1 /truth.json")
        else:
            # the chain's own height rate (two /status reads), never the explorer's figure
            h_a, t_a = (rd.get(a.chain, "/status") or {}).get("chain_head"), time.time(); time.sleep(3)
            h_b, t_b = (rd.get(a.chain, "/status") or {}).get("chain_head"), time.time()
            r10 = (h_b - h_a) / (t_b - t_a) if isinstance(h_a, int) and isinstance(h_b, int) and h_b > h_a else None
            if not r10: unread.append("X1 the chain's height rate (head did not move in 3 s)"); r10 = 0
            gen, stale_s = tj.get("generatedAtMs"), tj.get("staleAfterS")
            F = tj.get("facts") or {}
            if not isinstance(gen, (int, float)) or not isinstance(stale_s, (int, float)): unread.append("X1 truth.json has no generatedAtMs / staleAfterS")
            else:
                age = time.time() - gen / 1000
                ok(age <= stale_s + 60, f"X1 truth.json is {age:.0f} s old; it says it is stale after {stale_s} s")
            fixed = {"chainId": tr.get("chain_id"), "genesis": tr.get("genesis_sha256"), "release": {k: (tr.get("release") or {}).get(k) for k in ("state", "running")},
                     "seated": reg.get("active_count"), "agreedBy": (tr.get("committed") or {}).get("agreed_by")}
            for k, want in fixed.items(): eq(f"X1 truth.json {k}", (F.get(k) or {}).get("value"), want)
            moving = {"head": (st.get("chain_head"), r10), "finalized": (tr.get("finalized_height"), r10),
                      "certifiedBatch": ((tr.get("committed") or {}).get("certified_batch"), r10 / 16)}
            for k, (now, per_s) in moving.items():
                v = (F.get(k) or {}).get("value")
                if not isinstance(v, int) or not isinstance(now, int) or not per_s: unread.append(f"X1 {k}"); continue
                allow = per_s * ((stale_s if isinstance(stale_s, (int, float)) else 90) + 60)
                ok(v <= now + per_s * 5 and now - v <= allow, f"X1 truth.json {k} {v} vs the chain's {now} (allowed lag {int(allow)})")
        # X2
        lf = (sget("/api/live-facts") or {}).get("facts")
        if not lf: unread.append("X2 /api/live-facts")
        else:
            V = lambda x: x.get("value") if isinstance(x, dict) else None
            eq("X2 chain id", V(lf.get("chainId")), tr.get("chain_id"))
            eq("X2 genesis", V(lf.get("genesisSha256")), st.get("genesis_sha256"))
            eq("X2 trading open", V((lf.get("trading") or {}).get("open")), tr.get("trading_open"))
            eq("X2 deposits open", V((lf.get("deposits") or {}).get("open")), tr.get("deposits_open"))
            eq("X2 EVM live", V((lf.get("evm") or {}).get("live")), tr.get("evm_active"))
            eq("X2 validator count", V((lf.get("validators") or {}).get("count")), reg.get("active_count"))
            diff, only_chain, only_site = compare_upgrades(V((lf.get("upgrades") or {}).get("activations")), tr.get("rules"))
            for n, e, c in diff: fails.append(f"X2 upgrade '{n}': the explorer says {'on' if e else 'off'}, the chain says {'on' if c else 'off'}")
            for n in only_chain: fails.append(f"X2 upgrade '{n}' is on the chain's list but not the explorer's")
            agree += len(by_name(tr.get("rules"))) - len(diff) - len(only_chain)
        # X5: how far behind the chain the explorer's block index is (its newest indexed block vs the chain's head now)
        it = ((sget("/api/v2/blocks", limit=1) or {}).get("items") or [{}])[0]
        nb, ts = it.get("height"), it.get("timestamp")
        top = rd.get(a.chain, "/batches", from_height=0, to_height=0)["history"]["to_batch"] - 2
        if not isinstance(nb, int) or not ts: unread.append("X5 the explorer's newest indexed block")
        else:
            from datetime import datetime
            lag_s = time.time() - datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            h2 = (rd.get(a.chain, "/status") or {}).get("chain_head")
            if not isinstance(h2, int): h2 = nb
            print(f"  X5 the explorer's newest indexed block {nb} (made {ts}) · chain head {h2} · behind {h2 - nb:,} heights, {lag_s / 60:,.1f} min")
            ok(lag_s <= a.max_lag, f"X5 the explorer's block index is {round(lag_s)} s behind the chain (allowed {a.max_lag:g} s)")
            top = min(top, (nb - 1) // 16 - 2)          # X3 compares blocks the explorer has indexed
        # X3
        d = rd.get(a.chain, "/batches", from_height=top - a.batches + 1, to_height=top) or {}
        if not d.get("batches"): unread.append("X3 the chain's certificates for the window")
        for b in d.get("batches") or []:
            for h, hs in zip(b.get("heights") or [], b.get("block_hashes") or []):
                eb = sget(f"/api/blocks/{h}")
                if not isinstance(eb, dict) or not eb.get("hash"): unread.append(f"X3 block {h}"); continue
                ok(eb["hash"] == hs, f"X3 block {h}: the explorer serves {eb['hash']}, the certificate {hs}")
        # X4
        c1 = rd.get(a.chain, "/markets/specs") or {}; es = sget("/api/node/markets/specs") or {}; c2 = rd.get(a.chain, "/markets/specs") or {}
        P = lambda s: {p["pair"]["pair_id"]: p for p in ((s.get("specs") or {}).get("pairs") or []) if isinstance(p, dict) and p.get("pair")}
        if not es or not c1: unread.append("X4 market specs (explorer or chain)")
        else:
            p1, pe, p2 = P(c1), P(es), P(c2)
            for pid in sorted(p1):
                if p1[pid] != p2.get(pid): continue                       # moved between the two chain reads: not compared
                if pid not in pe: fails.append(f"X4 pair {pid} is in the chain's specs, not the explorer's"); continue
                ok(pe[pid] == p1[pid], f"X4 pair {pid}: the explorer's spec differs from the chain's")
    except (RuntimeError, OSError, KeyError, ValueError, TypeError, AttributeError) as x:
        print(f"NOT RUN: {x}"); return 2
    print(f"site {a.site} vs chain {a.chain}: {agree} values agree · {len(fails)} differ · {len(unread)} unread")
    for f in fails[:40]: print("  FAIL    " + f)
    for u in unread[:20]: print("  UNREAD  " + u)
    print(f"RESULT {'FAIL' if fails else ('NOTHING COMPARED' if not agree else ('INCOMPLETE' if unread else 'PASS'))}" + (f" ({len(unread)} unread, never passed)" if unread else ""))
    return 1 if fails else (3 if not agree else (2 if unread else 0))


def self_test():
    bad = 0
    def t(name, cond):
        nonlocal bad; bad += 0 if cond else 1; print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    rules = [{"name": "A", "active": True}, {"name": "B", "active": True}]
    t("U1 same on/off by name agrees", compare_upgrades([{"name": "A", "active": True}, {"name": "B", "active": True}], rules) == ([], [], []))
    t("U2 the explorer shows a live upgrade as off", compare_upgrades([{"name": "A", "active": True}, {"name": "B", "active": False}], rules)[0] == [("B", False, True)])
    t("U3 a chain upgrade missing on the explorer is named", compare_upgrades([{"name": "A", "active": True}], rules)[1] == ["B"])
    t("U4 an explorer-only name is listed apart (scheduled, not compared)", compare_upgrades([{"name": "A", "active": True}, {"name": "B", "active": True}, {"name": "C", "active": False}], rules)[2] == ["C"])
    print(f"self-test: {'PASS' if not bad else 'FAIL'}"); return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
