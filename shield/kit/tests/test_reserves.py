#!/usr/bin/env python3
"""Mutants of verify_reserves.py: each removes one rule; its self-test must then fail."""
import contextlib, io, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); KIT = os.path.dirname(HERE); sys.path.insert(0, KIT)
SRC = open(os.path.join(KIT, "verify_reserves.py")).read()
# Not listed (equivalent): skipping the early "unavailable" return — the status rule then fails it anyway (never covered).
MUTANTS = [
    ("liability not in the leaf", 'keccak256(b"\\x00" + addr + liab.to_bytes(16, "big"))', 'keccak256(b"\\x00" + addr)'),
    ("parent not ordered", "lo, hi = (a, b) if a <= b else (b, a)", "lo, hi = (a, b)"),
    ("walk end not compared", 'if h != root: return False, "the path does not lead', 'if False: return False, "the path does not lead'),
    ("coverage root not compared", 'if cr != root: return False', 'if False: return False'),
    ("other account accepted", 'if addr != mine: return False', 'if False: return False'),
    ("status rule not checked", "if st != want: fails.append", "if False: fails.append"),
    ("ratio not checked", "if bad_ratio: fails.append", "if False: fails.append"),
    ("zero-root rule not checked", "if (lc == 0) != (root == ZERO): fails.append", "if False: fails.append"),
    ("ratio rounded up", "rounding=ROUND_FLOOR", "rounding='ROUND_CEILING'"),
]


def run(src):
    m = {"__name__": "vr"}
    with contextlib.redirect_stdout(io.StringIO()):
        try: exec(compile(src, "verify_reserves.py", "exec"), m); return m["self_test"]()
        except Exception: return 1


bad = 0 if run(SRC) == 0 else 1
print(f"  clean self-test: {'PASS' if not bad else 'FAIL'}")
killed = 0
for name, a, b in MUTANTS:
    if SRC.count(a) != 1: print(f"  SITE NOT FOUND  {name}"); bad += 1; continue
    k = run(SRC.replace(a, b)) != 0; killed += k; bad += 0 if k else 1
    print(f"  {'KILLED' if k else 'SURVIVED'}  {name}")
print(f"test_reserves: {'PASS' if not bad else 'FAIL'} ({killed}/{len(MUTANTS)} mutants killed)"); sys.exit(1 if bad else 0)
