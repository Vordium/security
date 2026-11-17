"""A35 - TWAP orders by an agent, against its policy and after revoke. A positive control first: a TWAP on the agent's
allowed market is taken (it waits for a trigger far below the price, so nothing fills). Then (1) a TWAP on a market the
policy does not allow, and, after the owner revokes the agent, (2) a TWAP on its allowed market. Expected: the control
is taken; (1) refused by the agent's limits; (2) refused; neither is running."""
from shield import *

run = Run("A35", "agent TWAP outside its policy and after revoke")
net = Net(run)
s = setup_or_end(run, net)
owner, agent = s["owner"], s["agent"]
ctl = twap_body(net, s["agent_key"], owner, s["eth"])
r0 = post("/twap/place", ctl)
time.sleep(5)
run.step("control_allowed_market", http=r0["http"], answer=r0["answer"], running=bool(twap_running(owner, ctl["client_nonce"])))
if not (r0["http"] and r0["http"] < 300):
    run.end(CANNOT, f"the control TWAP on the allowed market was not taken ({r0['http']} {(r0['answer'] or {}).get('code')})")
b1 = twap_body(net, s["agent_key"], owner, net.pair("BTC"))
r1 = post("/twap/place", b1)
run.step("forbidden_market", http=r1["http"], answer=r1["answer"])
reason1 = agent_reason(r1["answer"])
r = submit(signed_op(s["owner_key"], "RevokeAgent", {"owner": owner, "agent": agent, "nonce": NONCE()}))
rev = wait_until(lambda: not is_live(agent_rec(owner, agent)), 25)
run.step("owner_revoke", http=r["http"], applied=bool(rev))
if not rev:
    run.end(CANNOT, "the owner's revoke did not apply")
b2 = twap_body(net, s["agent_key"], owner, s["eth"])
r2 = post("/twap/place", b2)
time.sleep(6)
run.step("after_revoke", http=r2["http"], answer=r2["answer"], running_forbidden=twap_running(owner, b1["client_nonce"]),
         running_after_revoke=twap_running(owner, b2["client_nonce"]))
if twap_running(owner, b1["client_nonce"]) or twap_running(owner, b2["client_nonce"]):
    run.end(WORKS, "a TWAP the agent may not place is running")
if not reason1:
    run.end(CANNOT, f"the forbidden-market TWAP was refused for another reason ({(r1['answer'] or {}).get('code')}), so the policy was not reached")
if not (r2["http"] and r2["http"] >= 400):
    run.end(WORKS, "a revoked agent's TWAP was taken at intake")
run.end(HOLDS, f"control taken; forbidden market refused ({reason1}); after revoke refused ({(r2['answer'] or {}).get('code')})")
