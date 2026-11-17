#!/usr/bin/env python3
"""Mutants of verify_history.py: each removes one rule; its self-test must then fail."""
import contextlib, io, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); KIT = os.path.dirname(HERE); sys.path.insert(0, KIT)
SRC = open(os.path.join(KIT, "verify_history.py")).read()
MUTANTS = [
    ("not-held passes", 'if b.get("certificate") != "held" or not b.get("qc"): return [], True', 'if not b.get("qc"): return [], True'),
    ("certificate block not checked", "if hs and (q.get(\"block_hash\") != hs[-1] or q.get(\"height\") != hh[-1]):", "if False:"),
    ("outside signer accepted", "if out: f.append", "if False: f.append"),
    ("quorum not checked", "if sum(seated.get(s, 0) for s in sg) < quorum:", "if False:"),
    ("heights range not checked", "if hh and (hh != sorted(set(hh)) or hh[0] < SIZE * n + 1 or hh[-1] > SIZE * n + SIZE):", "if False:"),
    ("overlap not checked", 'if prev and prev.get("heights") and hh and hh[0] <= prev["heights"][-1]:', "if False:"),
    ("block_count not checked", 'if not (len(hs) == len(hh) == b.get("block_count")):', "if False:"),
    ("repeated signer accepted", "if len(set(sg)) != len(sg) or q.get(\"signer_count\") != len(sg):", "if False:"),
    ("incomplete accepted", 'if b.get("complete") is not True:', "if False:"),
    ("digest in served order", "recs = sorted(recs, key=lambda r: tuple(int(x) for x in str(r.get(\"cursor\")).split(\".\")))", "pass"),
    ("no newline in canonical form", '+ b"\\n"', '+ b""'),
]


def run(src):
    m = {"__name__": "vh"}
    with contextlib.redirect_stdout(io.StringIO()):
        try: exec(compile(src, "verify_history.py", "exec"), m); return m["self_test"]()
        except Exception: return 1


bad = 0 if run(SRC) == 0 else 1
print(f"  clean self-test: {'PASS' if not bad else 'FAIL'}")
killed = 0
for name, a, b in MUTANTS:
    if SRC.count(a) != 1: print(f"  SITE NOT FOUND  {name}"); bad += 1; continue
    k = run(SRC.replace(a, b)) != 0; killed += k; bad += 0 if k else 1
    print(f"  {'KILLED' if k else 'SURVIVED'}  {name}")
print(f"test_history: {'PASS' if not bad else 'FAIL'} ({killed}/{len(MUTANTS)} mutants killed)"); sys.exit(1 if bad else 0)
