"""A14 - one agent attacks a sibling agent of the same owner: it signs RevokeAgent for the sibling, and a
SetAgentPolicyV1 that disables the sibling (a "tightening", but of someone else's policy). Expected: the sibling stays
live with its policy unchanged."""
from shield import *
from vordium.policy import policy_value

run = Run("A14", "agent revokes or disables a sibling agent")
net = Net(run)
s = setup_or_end(run, net)
sib = new_key(run, "sibling")
owner = s["owner"]
setup_agent(run, net, s["owner_key"], sib, "sibling", allowed_pair=s["eth"])
sa = addr(sib)
pol = lambda: {k: v for k, v in policy_of(agent_rec(owner, sa)).items() if k != "set_ms"}
p_before = pol()
r = submit(signed_op(s["agent_key"], "SetAgentPolicyV1",
                     policy_value(owner, sa, default_policy(s["exp"], enabled=False), NONCE())))
run.step("sent_disable_sibling", http=r["http"], answer=r["answer"])
ok1 = unchanged(run, "sibling_policy", pol, p_before, 12)
r = submit(signed_op(s["agent_key"], "RevokeAgent", {"owner": owner, "agent": sa, "nonce": NONCE()}))
run.step("sent_revoke_sibling", http=r["http"], answer=r["answer"])
ok2 = unchanged(run, "sibling_live", lambda: is_live(agent_rec(owner, sa)), True, 15)
if ok1 and ok2:
    run.end(HOLDS, "the sibling stayed live with its policy unchanged")
run.end(WORKS, "an agent changed or revoked a sibling agent")
