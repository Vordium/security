"""A47 - active hours that wrap past midnight (UTC). Two policies on two agents: a window that wraps and contains now,
and one that wraps and leaves out the hour around now. Each agent places a small stop (it rests with no margin).
Expected: the first rests; the second is refused, outside_active_window."""
from shield import *

D = 86_400_000
run = Run("A47", "active hours that wrap past midnight")
net = Net(run)
t = now_ms() % D
H = 3_600_000
inc = ((t + 1 * H) % D, (t + H // 2) % D)            # all day except [now+30 min, now+1 h): contains now, wraps
exc = ((t + H // 2) % D, (t - H // 2) % D)           # all day except [now-30 min, now+30 min): excludes now, wraps
res = {}
for label, (f, to) in (("wrap_contains_now", inc), ("wrap_excludes_now", exc)):
    if not f > to:
        run.end(CANNOT, "the window does not wrap at this time of day; run again in an hour")
    exp = now_ms() + 3600_000
    s = setup_or_end(run, net, label="-" + label, policy=default_policy(exp, active_from_ms_of_day=f, active_to_ms_of_day=to))
    b = dormant_stop(net, s["agent_key"], s["owner"], s["eth"])
    r = post("/order/place", b)
    rests = bool(wait_until(lambda: nonce_resting(s["owner"], b["clientNonce"]), 12))
    res[label] = {"http": r["http"], "reason": agent_reason(r["answer"]), "rests": rests}
    run.step(label, window=[f, to], http=r["http"], answer=r["answer"], rests=rests)
    owner_cancel_all_resting(run, s["owner_key"])
if not res["wrap_contains_now"]["rests"]:
    run.end(WORKS if res["wrap_contains_now"]["reason"] == "outside_active_window" else CANNOT,
            "the window that contains now refused the order: " + json.dumps(res))
if res["wrap_excludes_now"]["rests"]:
    run.end(WORKS, "an order outside a wrapped window rests")
if res["wrap_excludes_now"]["reason"] != "outside_active_window":
    run.end(CANNOT, "refused for another reason: " + json.dumps(res))
run.end(HOLDS, "inside the wrapped window it rests; outside it is refused (outside_active_window)")
