#!/usr/bin/env python3
"""A batch's trading-records digest, recomputed from public reads.

  verify_records_digest.py [<batch>] [--node URL] [--plant]

GET <node>/batch/<batch> gives records_digest (and records_digest_rule). This recomputes it from <node>/events/range over
the batch's heights: each record exactly as served, canonical JSON (keys sorted, separators ',' ':', no whitespace, UTF-8
unescaped) plus one newline, keccak256 over all of them in ascending cursor order (numeric per dotted part).
/events/range serves newest first: the records are sorted here. Without <batch>: the newest batch that has records.
--plant changes one record's field before hashing (a self-test: the digests must then differ).
Exit 0 equal (or, with --plant, different as it must be) · 1 not · 2 could not run."""
import argparse
import json
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))   # the shared helpers beside this file
from _common import TESTNET_NODE, get
from keccak import keccak256


def digest(records):
    return "0x" + keccak256(b"".join(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n" for r in records)).hex()


def records(node, b, size):
    lo, hi, out, cur = b * size + 1, b * size + size, [], None
    for _ in range(200):
        d = get(f"{node}/events/range?from={lo}&to={hi}&require_held=1" + (f"&cursor={cur}" if cur else ""))
        out += d.get("events") or []
        cur = d.get("next_cursor")
        if not cur:
            break
    return sorted(out, key=lambda r: tuple(int(x) for x in str(r.get("cursor")).split(".")))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch", nargs="?", type=int); ap.add_argument("--node", default=TESTNET_NODE); ap.add_argument("--plant", action="store_true")
    a = ap.parse_args()
    try:
        top = get(f"{a.node}/batches?from_height=0&to_height=0")["history"]["to_batch"]
        size = (min(get(f"{a.node}/batches?from_height={top}&to_height={top}")["batches"][0]["heights"]) - 1) // top
        b = a.batch
        if b is None:
            b = next(x for x in range(top - 3, top - 2000, -1) if (get(f"{a.node}/batch/{x}").get("records_count") or 0) > 0)
        bat = get(f"{a.node}/batch/{b}"); want = bat.get("records_digest")
        if want is None:
            print(f"batch {b}: the node gives no records digest"); sys.exit(2)
        recs = records(a.node, b, size)
        if a.plant and recs:
            recs[0] = {**recs[0], "kind": str(recs[0].get("kind")) + "_planted"}
        got = digest(recs); same = got == want
        print(f"batch {b}: {len(recs)} records (the node says {bat.get('records_count')}) · node {want} · recomputed {got} · {'EQUAL' if same else 'DIFFERENT'}{' (planted)' if a.plant else ''}")
        sys.exit((0 if not same else 1) if a.plant else (0 if same else 1))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"could not run: {type(e).__name__}: {e}"); sys.exit(2)
