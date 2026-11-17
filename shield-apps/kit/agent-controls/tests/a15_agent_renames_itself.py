"""A15 - an agent signs SetAgentName for itself (to pose as something the owner trusts). Expected: the name does not
change."""
from shield import *
from vordium.agent_ops import rename

run = Run("A15", "agent renames itself")
net = Net(run)
s = setup_or_end(run, net)
owner, agent = s["owner"], s["agent"]
read = lambda: rec_of(agent_rec(owner, agent)).get("name")
before = read()
op, val = rename(owner, agent, "Owner wallet", NONCE(), net.phase)
r = submit(signed_op(s["agent_key"], op, val))
run.step("sent", http=r["http"], answer=r["answer"])
if unchanged(run, "name", read, before, 15):
    run.end(HOLDS, "the agent-signed rename was not applied")
run.end(WORKS, "the chain renamed an agent on the agent's own signature")
