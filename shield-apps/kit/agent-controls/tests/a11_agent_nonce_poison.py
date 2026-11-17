"""A11 - nonce poisoning. An agent may sign a tightening of its own policy with its own nonce. It signs one with the
highest nonce it can, to stop the owner from revoking it.
Expected: after the agent's operation, the owner's own policy change and revoke still apply."""
import dataclasses, json
from shield import *
from vordium.policy import policy_value
from vordium.agent_ops import rename, submit_body
from vordium.eip712 import sign_agent_op

run = Run("A11", "agent poisons the nonce so the owner cannot revoke it")
net = Net(run)
results = {}
for label, big in (("2^53-1", 2 ** 53 - 1), ("2^64-1", 2 ** 64 - 1), ("1h_ahead", now_ms() + 3600_000),
                   ("23h_ahead", now_ms() + 23 * 3600_000)):
    s = setup_or_end(run, net, label=label.replace("^", "").replace("-", "m"))
    owner, agent = s["owner"], s["agent"]
    exp = s["exp"]
    tight = default_policy(exp, max_total_exposure_6dec=100 * E6)
    val = policy_value(owner, agent, tight, big)
    sig = sign_agent_op(s["agent_key"], "SetAgentPolicyV1", val)
    if big <= 2 ** 53 - 1:
        body = submit_body("SetAgentPolicyV1", val, sig)
    else:                                                   # the SDK will not write past 2^53-1; the wire can
        val2 = dict(val, nonce=2 ** 53 - 1)
        body = submit_body("SetAgentPolicyV1", val2, sig)
        body["nonce"] = big
    r = submit(body)
    took = wait_until(lambda: int(policy_of(agent_rec(owner, agent)).get("max_total_exposure_6dec") or 0) == 100 * E6, 15)
    run.step("agent_high_nonce", nonce=label, http=r["http"], answer=r["answer"], applied=bool(took))
    r_agent = r["http"]
    from vordium.agent_ops import set_policy
    op, v = set_policy(owner, agent, default_policy(exp, max_total_exposure_6dec=90 * E6), NONCE(), net.phase, now_ms())
    r = submit(signed_op(s["owner_key"], op, v))
    ren = wait_until(lambda: int(policy_of(agent_rec(owner, agent)).get("max_total_exposure_6dec") or 0) == 90 * E6, 20)
    run.step("owner_policy_after", http=r["http"], answer=r["answer"], applied=bool(ren))
    r = submit(signed_op(s["owner_key"], "RevokeAgent", {"owner": owner, "agent": agent, "nonce": NONCE()}))
    rev = wait_until(lambda: not is_live(agent_rec(owner, agent)), 25)
    run.step("owner_revoke_after", http=r["http"], answer=r["answer"], applied=bool(rev))
    results[label] = {"agent_op_applied": bool(took), "agent_op_intake": r_agent, "owner_policy": bool(ren), "owner_revoke": bool(rev)}
run.step("summary", results=results)
blocked = [k for k, v in results.items() if not (v["owner_policy"] and v["owner_revoke"])]
if blocked and any(results[k]["agent_op_applied"] for k in blocked):
    run.end(WORKS, "after the agent's high-nonce op the owner could not change or revoke it: " + ", ".join(blocked))
if not any(v["agent_op_applied"] for v in results.values()) and not all(v["owner_revoke"] for v in results.values()):
    run.end(CANNOT, "the owner's revoke did not apply even without a poisoned nonce")
if blocked:
    run.end(CANNOT, "an operation by the owner did not apply although the agent's op did not either: " + ", ".join(blocked))
run.end(HOLDS, "the owner's policy change and revoke applied after every high-nonce agent op " + json.dumps(results))
