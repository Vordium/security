#!/usr/bin/env python3
"""Proof of reserves, checked from public reads only.

  verify_reserves.py coverage [--node URL] [--rpc URL] [--plant-delta N]
      GET <node>/reserves/coverage. Each registered vault's USDC balance is read from a public Arbitrum RPC at the block the
      answer names for that vault (read[] matched by vault_id). Their sum must equal vault_usdc_6dec to the unit.
      coverage_ratio must equal floor(held / liabilities, 6 places), and status must follow the rule
      covered <=> held_6dec >= customer_liabilities_6dec. --plant-delta adds N base units to the answer before comparing
      (a self-test: the check must then fail).
      Not recomputed here: held's adjustments for in-flight deposits and payouts (they are the node's own figures).

  verify_reserves.py proof <address> [--node URL]
      Your inclusion proof: GET <node>/reserves/proof/<address>?height=<liabilities_height of the same coverage answer>.
      leaf = keccak256(0x00 || address || liability u128 big-endian), parent = keccak256(0x01 || min || max). The walk must
      reach the proof's root, which must equal the coverage answer's liabilities_root. It proves your balance is in the
      published tree; it does not prove the total.

Defaults: the test network (node https://testnet.vordex.xyz/chain, RPC Arbitrum Sepolia).
Exit 0 verified · 1 not verified · 2 could not run."""
import argparse
import sys
from decimal import Decimal, ROUND_FLOOR

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # the shared helpers beside this file
from _common import ARBITRUM_SEPOLIA_RPC, TESTNET_NODE, get, get_status, rpc
from keccak import keccak256


def coverage(node, rpc_url, plant):
    cv, vs = get(f"{node}/reserves/coverage"), get(f"{node}/bridge/v4/vaults")
    if cv.get("status") == "unavailable":
        print(f"the answer is unavailable: {cv.get('reason')} — nothing to reconcile"); return 2
    chain = int(rpc(rpc_url, "eth_chainId", []), 16)
    if {int(r["chain_id"]) for r in cv["read"]} != {chain}:
        print(f"the RPC serves chain {chain}; the answer read {cv['read']}"); return 2
    byid = {int(v["id"]): v for v in vs["vaults"]}
    bad, total = [], 0
    if sorted(int(r["vault_id"]) for r in cv["read"]) != sorted(byid):
        bad.append("the answer's read[] does not name exactly the registered vaults")
    for r in cv["read"]:
        v = byid.get(int(r["vault_id"]))
        if not v:
            continue
        data = "0x70a08231" + v["address"][2:].lower().rjust(64, "0")
        bal = int(rpc(rpc_url, "eth_call", [{"to": v["binding"]["usdc"], "data": data}, hex(int(r["block"]))]), 16)
        total += bal
        print(f"vault {r['vault_id']} {v['address']} at block {r['block']}: {bal / 1e6:,.6f} USDC")
    want = int(cv["vault_usdc_6dec"]) + plant
    print(f"sum {total / 1e6:,.6f} · the answer's vault USDC {want / 1e6:,.6f}")
    if total != want:
        bad.append(f"vault sum {total} != {want}")
    held, liab = int(cv["held_6dec"]), int(cv["customer_liabilities_6dec"])
    ratio = None if liab == 0 else str((Decimal(held) / Decimal(liab)).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR))
    print(f"held {held / 1e6:,.6f} · owed to customers {liab / 1e6:,.6f} · ratio {ratio} (answer {cv.get('coverage_ratio')}) · status {cv['status']}")
    if ratio != cv.get("coverage_ratio"):
        bad.append("ratio does not match")
    if cv["status"] != ("covered" if held >= liab else "not_covered"):
        bad.append("status does not follow held vs owed")
    print("VERIFIED" if not bad else "NOT VERIFIED: " + "; ".join(bad))
    return 0 if not bad else 1


def proof(node, address):
    a = address.lower()
    if not (a.startswith("0x") and len(a) == 42 and all(c in "0123456789abcdef" for c in a[2:])):
        print("an address is 0x and 40 hex characters"); return 2
    cv = get(f"{node}/reserves/coverage")
    root, height = cv.get("liabilities_root"), cv.get("liabilities_height")
    if not root or not height:
        print("the coverage answer has no liabilities root yet"); return 2
    st, p = get_status(f"{node}/reserves/proof/{a}?height={height}")
    if st == 404 and p and p.get("root"):
        print(f"no leaf for {a} at height {height}: nothing owed to this account in the tree"); return 1
    if st != 200 or not p:
        print(f"the proof could not be read (HTTP {st}{', the tree moved on: run again' if p and p.get('held_heights') else ''})"); return 2
    addr = bytes.fromhex(p["leaf"]["address"][2:]); liab = int(p["leaf"]["liability_6dec"])
    if addr != bytes.fromhex(a[2:]):
        print("NOT VERIFIED: the proof is for another account"); return 1
    h = keccak256(b"\x00" + addr + liab.to_bytes(16, "big"))
    if "leaf_hash" in p and bytes.fromhex(p["leaf_hash"][2:]) != h:
        print("NOT VERIFIED: the leaf hash does not match the leaf"); return 1
    for sib in (bytes.fromhex(x[2:]) for x in p["path"]):
        lo, hi = (h, sib) if h <= sib else (sib, h)
        h = keccak256(b"\x01" + lo + hi)
    if "0x" + h.hex() != p["root"].lower():
        print("NOT VERIFIED: the path does not reach the proof's root"); return 1
    if p["root"].lower() != root.lower():
        print("NOT VERIFIED: the proof's root is not the coverage answer's root"); return 1
    print(f"VERIFIED: {a} — {liab / 1e6:,.6f} USDC owed, in the tree at height {height} under root {root}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["coverage", "proof"]); ap.add_argument("address", nargs="?")
    ap.add_argument("--node", default=TESTNET_NODE); ap.add_argument("--rpc", default=ARBITRUM_SEPOLIA_RPC)
    ap.add_argument("--plant-delta", type=int, default=0)
    a = ap.parse_args()
    try:
        sys.exit(coverage(a.node, a.rpc, a.plant_delta) if a.what == "coverage" else proof(a.node, a.address or ""))
    except Exception as e:  # noqa: BLE001
        print(f"could not run: {type(e).__name__}: {e}"); sys.exit(2)
