"""A22 - an agent signs SetMmp (market maker protection) for its owner: a tiny limit freezes the owner's quoting.
Expected: refused; the owner's account settings do not change."""
from shield import *
from vordium import mm

run = Run("A22", "agent sets its owner's market maker protection")
net = Net(run)
s = setup_or_end(run, net)
owner = s["owner"]
read = lambda: get(f"/markets/account/{owner}")
before = read()
m = mm.Mmp(window_ms=1000, max_fills=1, freeze_ms=60_000)
n = NONCE()
sig = mm.sign(s["agent_key"], mm.digest(mm.set_mmp_struct_hash(owner, m, n), separator("VordCore")))
r = post("/account/mmp", mm.mmp_body(owner, m, n, sig))
run.step("sent", http=r["http"], answer=r["answer"])
strip = lambda j: {k: v for k, v in (j or {}).items() if "mmp" in k.lower()} if isinstance(j, dict) else j
if unchanged(run, "mmp", lambda: strip(read()), strip(before), 12):
    run.end(HOLDS, f"the owner's protection settings did not change (intake {r['http']})")
run.end(WORKS, "an agent's signature changed the owner's market maker protection")
