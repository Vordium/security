"""A45 - an agent and the owner's app session sign for the same account. Control: the agent places a stop of its own and
cancel-all takes it (the route takes the agent's cancels). Then the session places a stop (it rests with no margin, far from the
price); the agent cancels it, then sends cancel-all. Expected: the control goes; the session's order survives."""
from shield import *
from vordium import mm
from vordium.account_ops import AccountOps

run = Run("A45", "agent cancels the app session's order")
net = Net(run)
s = setup_or_end(run, net)
sk = new_key(run, "session")
res = AccountOps(s["owner_key"]).create_session(addr(sk), now_ms() + 3600_000, wait_s=40)
run.step("owner_session", applied=res.applied)
if res.applied is not True:
    run.end(CANNOT, "the owner's session could not be created")
own = dormant_stop(net, s["agent_key"], s["owner"], s["eth"])
ro = post("/order/place", own)
mine = wait_until(lambda: nonce_resting(s["owner"], own["clientNonce"]), 15)
if not mine:
    run.end(CANNOT, "the agent's own control stop did not rest")
n0 = NONCE()
sg = mm.sign(s["agent_key"], mm.digest(mm.cancel_all_struct_hash(s["owner"], 0, n0), separator("VordCore")))
rc = post("/order/cancel-all", mm.cancel_all_body(s["owner"], 0, n0, sg))
gone = wait_until(lambda: not nonce_resting(s["owner"], own["clientNonce"]), 20)
run.step("control_agent_cancel_all_own", http=rc["http"], answer=rc["answer"], cancelled=bool(gone))
if not gone:
    run.end(CANNOT, "the agent's cancel-all did not take its own order, so a refusal of the session's order proves nothing")
b = dormant_stop(net, sk, s["owner"], s["eth"])
r = post("/order/place", b)
rest = wait_until(lambda: nonce_resting(s["owner"], b["clientNonce"]), 15)
run.step("session_stop", http=r["http"], answer=r["answer"], rests=bool(rest))
if not rest:
    run.end(CANNOT, "the session's stop did not rest")
oid = int(rest[0].get("id", rest[0].get("order_id")))
r1 = post("/order/cancel", cancel_body(s["agent_key"], s["owner"], oid))
n = NONCE()
sig = mm.sign(s["agent_key"], mm.digest(mm.cancel_all_struct_hash(s["owner"], 0, n), separator("VordCore")))
r2 = post("/order/cancel-all", mm.cancel_all_body(s["owner"], 0, n, sig))
time.sleep(6)
still = bool(nonce_resting(s["owner"], b["clientNonce"]))
run.step("after", cancel=[r1["http"], r1["answer"]], cancel_all=[r2["http"], r2["answer"]], session_order_rests=still)
owner_cancel_all_resting(run, s["owner_key"])
if not still:
    run.end(WORKS, "the agent cancelled an order the app session placed")
run.end(HOLDS, "control cancelled; the session's order survived the agent's cancel and cancel-all")
