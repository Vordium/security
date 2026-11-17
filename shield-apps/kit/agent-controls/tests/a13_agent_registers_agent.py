"""A13 - an agent signs RegisterAgentV2 for its owner, registering a new key it controls (an agent minting agents
with no policy of the owner's). Expected: the new key is never an agent of the owner."""
from shield import *
from vordium.agent_ops import registration

run = Run("A13", "agent registers another agent for its owner")
net = Net(run)
s = setup_or_end(run, net)
child = new_key(run, "child")
owner, ca = s["owner"], addr(child)
op, val = registration(owner, ca, "made by an agent", now_ms() + 3600_000, NONCE(), net.phase, name="child agent")
r = submit(signed_op(s["agent_key"], op, val))
run.step("sent", http=r["http"], answer=r["answer"])
read = lambda: agent_rec(owner, ca).get("found")
if unchanged(run, "child_found", read, read(), 15) and not is_live(agent_rec(owner, ca)):
    run.end(HOLDS, "the key the agent registered is not an agent of the owner")
run.end(WORKS, "the chain registered an agent signed by another agent")
