"""A48 - the dead-man switch, armed by the owner's app session (a session key may arm it; an agent may not, see A20).
The session places a stop (it rests with no margin), then arms the switch 25 s ahead and never refreshes it.
Expected: at the deadline the stop is cancelled and new orders are refused; the owner then clears the switch."""
from shield import *
from vordium import schedule_cancel as SC
from vordium.account_ops import AccountOps

run = Run("A48", "the dead-man switch fires")
net = Net(run)
s = setup_or_end(run, net)
owner = s["owner"]
st = get(f"/schedule-cancel/{owner}")
if not (isinstance(st, dict) and st.get("active") is True):
    run.end(CANNOT, "the dead-man switch is not active on this network")
sk = new_key(run, "session")
res = AccountOps(s["owner_key"]).create_session(addr(sk), now_ms() + 3600_000, wait_s=40)
run.step("owner_session", applied=res.applied)
if res.applied is not True:
    run.end(CANNOT, "the owner's session could not be created")
b = dormant_stop(net, sk, owner, s["eth"])
r = post("/order/place", b)
rest = wait_until(lambda: nonce_resting(owner, b["clientNonce"]), 15)
run.step("session_stop", http=r["http"], rests=bool(rest))
if not rest:
    run.end(CANNOT, "the session's stop did not rest")
sep = separator("VordCore")
lead = int(((st.get("limits") or {}).get("min_lead_ms") or 20_000)) + 5_000
T, n = now_ms() + lead, NONCE()
r = post("/schedule-cancel", SC.schedule_cancel_body(owner, T, n, SC.sign_schedule_cancel(sk, owner, T, n, domain_separator=sep)))
armed = wait_until(lambda: (get(f"/schedule-cancel/{owner}") or {}).get("cancel_at_ms") == T, 15)
run.step("session_arms", http=r["http"], answer=r["answer"], armed=bool(armed), at=T)
if not armed:
    run.end(CANNOT, "the session could not arm the switch")
fired = wait_until(lambda: (get(f"/schedule-cancel/{owner}") or {}).get("fired") is True, (lead / 1000) + 40, 2)
gone = not nonce_resting(owner, b["clientNonce"])
nb = dormant_stop(net, sk, owner, s["eth"])
rn = post("/order/place", nb)
run.step("after_deadline", state=get(f"/schedule-cancel/{owner}"), stop_cancelled=gone, new_order=[rn["http"], rn["answer"]])
n2 = NONCE()
rc = post("/schedule-cancel", SC.schedule_cancel_body(owner, 0, n2, SC.sign_schedule_cancel(s["owner_key"], owner, 0, n2, domain_separator=sep)))
run.step("owner_clears", http=rc["http"], answer=rc["answer"])
owner_cancel_all_resting(run, s["owner_key"])
if not fired:
    run.end(WORKS, "the switch did not fire at its deadline")
if not gone or (rn["http"] and rn["http"] < 300 and nonce_resting(owner, nb["clientNonce"])):
    run.end(WORKS, "after the deadline an order stayed or a new one was taken")
run.end(HOLDS, "at the deadline the stop was cancelled and a new order refused")
