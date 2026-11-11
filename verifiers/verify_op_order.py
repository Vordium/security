#!/usr/bin/env python3
"""Each block's operation-order digest, checked from public reads on two endpoints.

  verify_op_order.py [blocks=4]   (most heights are empty slots: each block costs a walk; about 45 s for 4) [--a URL] [--b URL] [--plant]

For recent blocks with operations, GET /block/<height>/ops gives op_keccaks (each operation's hash, in block order) and
ops_order_digest. Checked here: ops_order_digest == keccak256(concatenation of op_keccaks), and the second endpoint serves the
same op_keccaks and digest for the same block. --plant swaps two operations (a self-test: the digest must then differ).
Not recomputed here: each operation's own hash (it needs the node's binary encoding).
Exit 0 all equal (or, with --plant, different) · 1 not · 2 could not run."""
import argparse
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # the shared helpers beside this file
from _common import TESTNET_ARCHIVE, TESTNET_NODE, get
from keccak import keccak256


def digest(ks):
    return "0x" + keccak256(b"".join(bytes.fromhex(k[2:]) for k in ks)).hex()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blocks", nargs="?", type=int, default=4); ap.add_argument("--a", default=TESTNET_NODE)
    ap.add_argument("--b", default=TESTNET_ARCHIVE); ap.add_argument("--plant", action="store_true")
    o = ap.parse_args()
    try:
        top = get(f"{o.a}/batches?from_height=0&to_height=0")["history"]["to_batch"]
        first = min(get(f"{o.a}/batches?from_height={top}&to_height={top}")["batches"][0]["heights"]); size = (first - 1) // top
        h, seen, ok, bad, nulls = first - 2 * size, 0, 0, 0, 0
        for _ in range(4000):
            if seen >= o.blocks:
                break
            h -= 1
            a = get(f"{o.a}/block/{h}/ops")
            if not isinstance(a, dict):        # an empty slot (a batch spans more heights than blocks)
                continue
            ks = a.get("op_keccaks") or []
            if not ks or (o.plant and len(ks) < 2):
                continue
            seen += 1
            if any(k is None for k in ks):
                nulls += 1; print(f"block {h}: an operation without a hash — not verifiable here"); continue
            if o.plant:
                sw = ks[:]; sw[0], sw[1] = sw[1], sw[0]; good = digest(sw) != a.get("ops_order_digest")
                print(f"block {h}: two operations swapped → {'DIFFERENT (as it must be)' if good else 'the same — the self-test did not fire'}")
            else:
                b = get(f"{o.b}/block/{h}/ops"); b = b if isinstance(b, dict) else {}
                same_b = b.get("op_keccaks") == ks and b.get("ops_order_digest") == a.get("ops_order_digest")
                good = digest(ks) == a.get("ops_order_digest") and same_b
                print(f"block {h}: {len(ks)} operations · recomputed {'=' if digest(ks) == a.get('ops_order_digest') else '!='} node · second endpoint {'agrees' if same_b else 'DIFFERS'}")
            ok += good; bad += not good
        print(f"RESULT {'PASS' if bad == 0 and ok else 'FAIL'} · {ok} ok, {bad} not, {nulls} with an operation without a hash")
        sys.exit(0 if bad == 0 and ok else 1)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"could not run: {type(e).__name__}: {e}"); sys.exit(2)
