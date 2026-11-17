#!/usr/bin/env python3
"""Verify the chain's proof of reserves from public reads only.

  R1  the coverage answer follows its own stated rule: status covered exactly when held >= customer liabilities (both read),
      coverage_ratio = floor(held / liabilities, 6 places) (null when nothing is owed); "unavailable" is never a pass;
  R2  the vaults' USDC, read by YOU on Arbitrum at the block the answer names for each vault, adds up to vault_usdc to the unit
      (needs --arbitrum-rpc; skipped and said so otherwise);
  R3  the liabilities tree: no leaves <=> the all-zero root; a second host (--second-chain) publishes the same root for the
      same height;
  R4  your account (--address): the proof's leaf is your address, its path walks to the proof's root by the published rule,
      and that root is the coverage answer's liabilities_root at the same height. An account with nothing owed has no leaf:
      "not in the tree" is the chain's claim, backed here only by the account's balance NOW (no public read gives the balance
      at the tree's height), so an account that held funds then and has emptied it since cannot be told apart.
Limits (by design, stated by the chain): the tree proves inclusion, not the total (a Merkle-sum tree is planned); held's
in-flight terms (deposits not yet credited, payouts not yet settled) come from the vault contracts' own totals. R2 reads the
USDC token address the chain names for each vault (binding.usdc): check that it is the official USDC contract on that network.

Usage:  python3 verify_reserves.py --chain https://testnet.vordex.xyz/chain [--arbitrum-rpc URL] [--address 0x…] [--second-chain URL]
        python3 verify_reserves.py --self-test
Exit:   0 = every check run passed · 1 = a check failed · 2 = could not run / unavailable · 3 = nothing checked."""
import argparse, json, os, random, sys
from decimal import Decimal, ROUND_FLOOR
from vordium_check.common import Reader, keccak256

ZERO = "0x" + "00" * 32


NO_LEAF = "no leaf for this address at this height"


def hx(s, n):
    if not isinstance(s, str) or not s.startswith("0x") or len(s) != 2 + 2 * n: return None
    try: return bytes.fromhex(s[2:])
    except ValueError: return None


def leaf_hash(addr: bytes, liab: int) -> bytes: return keccak256(b"\x00" + addr + liab.to_bytes(16, "big"))


def parent(a: bytes, b: bytes) -> bytes:
    lo, hi = (a, b) if a <= b else (b, a)
    return keccak256(b"\x01" + lo + hi)


def walk(proof, address, root_from_coverage):
    """(ok, why, liability_6dec)"""
    mine, addr = hx(address.lower() if isinstance(address, str) else None, 20), hx((proof.get("leaf") or {}).get("address", "").lower(), 20)
    root, path = hx(proof.get("root"), 32), proof.get("path")
    v = (proof.get("leaf") or {}).get("liability_6dec")
    liab = int(v) if isinstance(v, str) and v.isdigit() else (v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None)
    if mine is None: return False, "not an account address", None
    if addr is None or liab is None or liab >= 1 << 128 or root is None or not isinstance(path, list): return False, "proof not in the published shape", None
    sib = [hx(p, 32) for p in path]
    if any(s is None for s in sib): return False, "a path entry is not a 32-byte hash", None
    if addr != mine: return False, "the proof is for another account", None
    h = leaf_hash(addr, liab)
    if proof.get("leaf_hash") is not None and hx(proof["leaf_hash"], 32) != h: return False, "the leaf hash does not match the leaf", None
    for s in sib: h = parent(h, s)
    if h != root: return False, "the path does not lead to the proof's root", None
    cr = hx(root_from_coverage, 32)
    if cr is None: return False, "the coverage answer's root could not be read", None
    if cr != root: return False, "the proof's root is not the coverage answer's liabilities_root", None
    return True, "included", liab


def strict_int(v):
    if isinstance(v, bool) or not (isinstance(v, int) or (isinstance(v, str) and v.isdigit())): raise ValueError(f"not a whole number: {v!r}")
    return int(v)


def ratio(held, liab):
    return None if liab == 0 else (Decimal(held) / Decimal(liab)).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)


def check_coverage(cv):
    """R1 + R3 (local part). Returns (fails, notes)."""
    fails, notes = [], []
    st = cv.get("status")
    if st == "unavailable": return [f"coverage is unavailable: {cv.get('reason')}"], notes
    try: held, liab = strict_int(cv["held_6dec"]), strict_int(cv["customer_liabilities_6dec"])
    except (KeyError, TypeError, ValueError): return ["held or liabilities missing or not whole numbers"], notes
    want = "covered" if held >= liab else "not_covered"
    if st != want: fails.append(f"R1 status {st} but held {held} vs liabilities {liab} says {want}")
    r, a = ratio(held, liab), cv.get("coverage_ratio")
    try: bad_ratio = (r is None) != (a is None) or (r is not None and Decimal(str(a)) != r)
    except ArithmeticError: bad_ratio = True
    if bad_ratio: fails.append(f"R1 coverage_ratio {a} but floor(held/liabilities) = {r}")
    lc, root = cv.get("leaf_count"), cv.get("liabilities_root")
    if (lc == 0) != (root == ZERO): fails.append(f"R3 leaf_count {lc} with root {root}: no leaves must mean the zero root and back")
    notes.append(f"held {held / 1e6:,.6f} · liabilities {liab / 1e6:,.6f} · ratio {a} · status {st} · leaves {lc} at height {cv.get('liabilities_height')}")
    return fails, notes


def arbitrum_sum(rpc_url, cv, vaults, plant=0):
    import urllib.request
    def rpc(method, params):
        req = urllib.request.Request(rpc_url, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                     {"content-type": "application/json", "user-agent": "vordium-rerun-kit/1"})
        r = json.load(urllib.request.urlopen(req, timeout=30))
        if "error" in r: raise RuntimeError(r["error"])
        return r["result"]
    chain = int(rpc("eth_chainId", []), 16); byid = {int(v["id"]): v for v in vaults}
    fails, total = [], 0
    if {int(r["chain_id"]) for r in cv["read"]} != {chain}: return [f"R2 this RPC is chain {chain}; the answer read chain(s) {sorted({r['chain_id'] for r in cv['read']})}"], 0
    if sorted(int(r["vault_id"]) for r in cv["read"]) != sorted(byid): fails.append(f"R2 the answer read vaults {[r['vault_id'] for r in cv['read']]}, the chain lists {sorted(byid)}")
    for r in cv["read"]:
        v = byid.get(int(r["vault_id"]))
        if not v: continue
        total += int(rpc("eth_call", [{"to": v["binding"]["usdc"], "data": "0x70a08231" + v["address"][2:].rjust(64, "0")}, hex(int(r["block"]))]), 16)
    want = int(cv["vault_usdc_6dec"]) + plant
    if total != want: fails.append(f"R2 the vaults hold {total} on Arbitrum; the answer says {want}")
    return fails, total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chain"); ap.add_argument("--arbitrum-rpc"); ap.add_argument("--address"); ap.add_argument("--second-chain")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return self_test()
    if not a.chain: ap.error("--chain is required")
    rd, fails, ran, unread = Reader(), [], [], False
    try:
        cv, proof = None, None
        for _ in range(4):   # the coverage answer and the proof at ONE tree height (a node keeps only its newest trees)
            cv = rd.get(a.chain, "/reserves/coverage")
            if not cv or not a.address: break
            proof = rd.get(a.chain, f"/reserves/proof/{a.address.lower()}", keep_404=True, height=cv.get("liabilities_height"))
            if not (isinstance(proof, dict) and proof.get("error") == "height not held"): break
        if not cv: print("NOT RUN: this host does not serve the coverage answer"); return 2
        f, notes = check_coverage(cv); fails += f; ran.append("R1"); [print("  " + n) for n in notes]
        if cv.get("status") == "unavailable": print("RESULT UNAVAILABLE (never a pass): " + "; ".join(f)); return 2
        if a.arbitrum_rpc:
            vs = rd.get(a.chain, "/bridge/v4/vaults") or {}
            f, total = arbitrum_sum(a.arbitrum_rpc, cv, vs.get("vaults") or [], int(os.environ.get("PLANT_DELTA_6DEC", "0")))
            fails += f; ran.append("R2"); print(f"  vaults on Arbitrum: {total / 1e6:,.6f} USDC · answer {int(cv['vault_usdc_6dec']) / 1e6:,.6f}")
        else: print("  R2 skipped: no --arbitrum-rpc given")
        if a.second_chain:
            h = cv.get("liabilities_height"); cv2 = rd.get(a.second_chain, "/reserves/coverage") or {}
            if cv2.get("liabilities_height") == h and h is not None:
                ran.append("R3")
                if str(cv2.get("liabilities_root")).lower() != str(cv.get("liabilities_root")).lower(): fails.append(f"R3 the second host publishes root {cv2.get('liabilities_root')} for height {h}")
                else: print(f"  second host: same root at height {h}")
            else: print(f"  R3 UNREAD: the second host is at tree height {cv2.get('liabilities_height')} (not {h}); run again"); unread = True
        if a.address:
            p = proof
            if not isinstance(p, dict) or p.get("error") == "height not held": print(f"  R4 UNREAD: the proof route did not answer for {a.address} (never a pass)"); unread = True
            elif "error" in p:
                if p.get("error") != NO_LEAF: print(f"  R4 UNREAD: the proof route answered {p.get('error')!r}"); unread = True
                elif p.get("height") != cv.get("liabilities_height") or str(p.get("root")).lower() != str(cv.get("liabilities_root")).lower():
                    fails.append(f"R4 the no-leaf answer is for height {p.get('height')} / root {p.get('root')}, not the coverage answer's")
                else:
                    # NOT IN THE TREE is the chain's own claim; it is backed only by the account's balance read now
                    bal = rd.get(a.chain, f"/balance/{a.address.lower()}") or {}
                    tot = bal.get("total")
                    if isinstance(tot, int) and not isinstance(tot, bool) and tot == 0:
                        ran.append("R4"); print(f"  {a.address}: NOT IN THE TREE at height {p.get('height')}, and its balance now is 0 — nothing owed")
                    else:
                        unread = True
                        print(f"  R4 NOT IN THE TREE (the chain's claim) at height {p.get('height')}, but the balance now is {tot!r}: "
                              "if the account held funds at that height this is a fault — run again; if it persists, report it")
            else:
                ran.append("R4")
                ok, why, liab = walk(p, a.address, cv.get("liabilities_root"))
                if ok: print(f"  {a.address}: INCLUDED, liability {liab / 1e6:,.6f} USDC at height {cv.get('liabilities_height')}")
                else: fails.append(f"R4 {why}")
    except (RuntimeError, OSError, KeyError, ValueError, TypeError, AttributeError, ArithmeticError) as x:
        print(f"NOT RUN: {x}"); return 2
    for f in fails: print("  FAIL  " + f)
    not_cov = cv.get("status") == "not_covered"
    verdict = "FAIL" if fails else ("NOT COVERED (the answer is consistent: the vaults hold less than is owed)" if not_cov else ("INCOMPLETE" if unread else "PASS"))
    print(f"RESULT {verdict} (checks run: {', '.join(ran)})" + (" · a check you asked for was unread (never a pass)" if unread else ""))
    return 1 if fails or not_cov else (2 if unread else (0 if ran else 3))


def build_tree(leaves):
    """leaves: [(addr bytes, liab)] -> (root, {addr: path}) by the published rule (for the self-test)."""
    lv = sorted(leaves); level = [leaf_hash(a, l) for a, l in lv]; pos = {a: i for i, (a, _) in enumerate(lv)}
    paths = {a: [] for a, _ in lv}
    if not level: return bytes(32), paths
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level): nxt.append(parent(level[i], level[i + 1]))
            else: nxt.append(level[i])
        for a in paths:
            i = pos[a]; j = i ^ 1
            if j < len(level): paths[a].append(level[j])
            pos[a] = i // 2
        level = nxt
    return level[0], paths


def self_test():
    random.seed(7); bad = 0
    def t(name, cond):
        nonlocal bad; bad += 0 if cond else 1; print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    leaves = [(bytes(random.getrandbits(8) for _ in range(20)), random.randint(1, 10**12)) for _ in range(13)]
    root, paths = build_tree(leaves); R = "0x" + root.hex()
    def proof(a, l, p=None, r=None): return {"leaf": {"address": "0x" + a.hex(), "liability_6dec": str(l)}, "path": ["0x" + x.hex() for x in (paths[a] if p is None else p)], "root": r or R}
    a0, l0 = leaves[0]; a5, l5 = leaves[5]
    t("P1 every leaf of a 13-leaf tree (odd levels carried) verifies", all(walk(proof(a, l), "0x" + a.hex(), R)[0] for a, l in leaves))
    t("P2 a changed liability fails", not walk(proof(a0, l0 + 1), "0x" + a0.hex(), R)[0])
    t("P3 a changed sibling fails", not walk(proof(a0, l0, [bytes(32)] + paths[a0][1:]), "0x" + a0.hex(), R)[0])
    t("P4 someone else's proof fails for my address", not walk(proof(a5, l5), "0x" + a0.hex(), R)[0])
    t("P5 a proof to another root fails against the coverage root", not walk(proof(a0, l0), "0x" + a0.hex(), "0x" + "11" * 32)[0])
    t("P6 a dropped path entry fails", not walk(proof(a0, l0, paths[a0][:-1]), "0x" + a0.hex(), R)[0])
    t("P7 keccak256 of 'abc' is the known value", keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")
    cv = {"status": "covered", "held_6dec": "200", "customer_liabilities_6dec": "100", "coverage_ratio": "2.000000", "leaf_count": 3, "liabilities_root": R}
    t("C1 a consistent covered answer passes", check_coverage(cv)[0] == [])
    t("C2 covered while held < liabilities fails", check_coverage({**cv, "held_6dec": "99", "coverage_ratio": "0.990000"})[0] != [])
    t("C3 a wrong ratio fails", check_coverage({**cv, "coverage_ratio": "2.000001"})[0] != [])
    t("C4 nothing owed: ratio null, covered", check_coverage({**cv, "customer_liabilities_6dec": "0", "coverage_ratio": None, "leaf_count": 0, "liabilities_root": ZERO})[0] == [])
    t("C5 leaves with the zero root fails", check_coverage({**cv, "liabilities_root": ZERO})[0] != [])
    t("C6 unavailable is never a pass, even with consistent figures", check_coverage({**cv, "status": "unavailable", "reason": "x"})[0] != [])
    t("C8 the ratio is floored (2/3 = 0.666666)", check_coverage({**cv, "held_6dec": "2", "customer_liabilities_6dec": "3", "status": "not_covered", "coverage_ratio": "0.666666"})[0] == [])
    t("C7 ratio given as a number is read the same", check_coverage({**cv, "coverage_ratio": 2.0})[0] == [])
    print(f"self-test: {'PASS' if not bad else 'FAIL'}"); return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
