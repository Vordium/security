"""A19 - an agent signs StopAllSigners for its owner (which would stop the owner's session and every agent).
Expected: refused; the agent and the owner's session stay."""
from shield import *
from vordium.account_ops import AccountOps

FIELDS = [("owner", "address"), ("nonce", "uint256"), ("validUntil", "uint256")]
run = Run("A19", "agent stops all of its owner's signers")
net = Net(run)
probe = post("/signers/stop-all", {})
run.step("route", http=probe["http"], answer=probe["answer"])
if probe["http"] in (404, 405) or (isinstance(probe["answer"], dict) and probe["answer"].get("code") == "not_in_force"):
    run.end(CANNOT, "the network does not take StopAllSigners")
s = setup_or_end(run, net)
sk = new_key(run, "session")
owner, agent = s["owner"], s["agent"]
res = AccountOps(s["owner_key"]).create_session(addr(sk), now_ms() + 3600_000, wait_s=40)
run.step("owner_session", applied=res.applied)
if res.applied is not True:
    run.end(CANNOT, "the owner's session did not apply, so the stop of the owner's signers cannot be judged")
v = {"owner": owner, "nonce": NONCE(), "validUntil": now_ms() // 1000 + 120}
sig = typed_sign(s["agent_key"], "VordexSession", "StopAllSigners", FIELDS, v)
r = post("/signers/stop-all", {**v, "signature": sig})
run.step("sent", http=r["http"], answer=r["answer"])
time.sleep(8)
live = is_live(agent_rec(owner, agent))
sess = (get(f"/session/get?owner={owner}") or {}).get("session_key")
signers = get(f"/signers/{owner}")
run.step("after", agent_live=live, session=sess, signers=signers)
if live and sess:
    run.end(HOLDS, f"nothing was stopped (intake {r['http']})")
run.end(WORKS, "an agent's StopAllSigners stopped its owner's signers")
