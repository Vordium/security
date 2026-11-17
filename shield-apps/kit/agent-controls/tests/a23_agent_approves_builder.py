"""A23 - an agent signs ApproveBuilderFee for its owner, naming a builder address it controls at the highest fee
(every later order of the owner could then pay that builder). Expected: refused; the owner's approvals do not change."""
from shield import *
from vordium import builder as B

run = Run("A23", "agent approves a builder fee for its owner")
net = Net(run)
s = setup_or_end(run, net)
owner = s["owner"]
attacker = new_key(run, "builder")
read = lambda: get(f"/builder/approvals/{owner}")
before = read()
run.step("before", approvals=before)
nonce = int((before or {}).get("nonce") or 0) + 1 if isinstance(before, dict) else 1
msg = {"user": owner, "builder": addr(attacker), "maxFeeCbps": 10_000, "nonce": nonce, "validUntil": now_ms() // 1000 + 120}
sig = B.sign(s["agent_key"], B.digest("ApproveBuilderFee", msg, separator("VordCore")))
r = post("/builder/approve", {**msg, "signature": sig})
run.step("sent", http=r["http"], answer=r["answer"])
if unchanged(run, "approvals", read, before, 12):
    run.end(HOLDS, f"no builder approval was made (intake {r['http']})")
run.end(WORKS, "an agent's signature approved a builder fee for its owner")
