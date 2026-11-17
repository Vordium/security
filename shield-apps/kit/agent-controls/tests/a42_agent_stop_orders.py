"""A42 - stop orders by an agent. A stop rests with no margin and becomes an order only when the mark reaches its
trigger. A positive control first: a small stop on the allowed market, far from the price, is taken and rests. Then a
stop on a market the policy does not allow, and one above the largest order. Expected: both refused when placed. The
network's spec says an agent's stop is judged again when it fires; that second check is not exercised here (it needs
the mark to reach the trigger)."""
from shield import *

run = Run("A42", "agent stop orders judged against its limits")
net = Net(run)
s = setup_or_end(run, net)
eth = s["eth"]
ctl = dormant_stop(net, s["agent_key"], s["owner"], eth)
r0 = post("/order/place", ctl)
rests = wait_until(lambda: nonce_resting(s["owner"], ctl["clientNonce"]), 15)
run.step("control_stop", http=r0["http"], answer=r0["answer"], rests=bool(rests))
if not rests:
    run.end(CANNOT, f"the control stop inside every limit did not rest ({r0['http']} {(r0['answer'] or {}).get('code')})")
btc = net.pair("BTC")
lot = int(eth["lot18dec"])
res = {}
for label, body in (("forbidden_market", dormant_stop(net, s["agent_key"], s["owner"], btc)),
                    ("above_largest_order", stop_body(s["agent_key"], s["owner"], eth["pairId"], 0, lot * 3000,
                                                      int(ctl["trigger_price_8dec"]), 1))):
    r = post("/order/place", body)
    time.sleep(5)
    res[label] = {"http": r["http"], "reason": agent_reason(r["answer"]), "rests": bool(nonce_resting(s["owner"], body["clientNonce"]))}
    run.step(label, http=r["http"], answer=r["answer"], rests=res[label]["rests"])
owner_cancel_all_resting(run, s["owner_key"])
if any(v["rests"] for v in res.values()):
    run.end(WORKS, "a stop outside the agent's limits rests: " + json.dumps(res))
if not all(v["reason"] for v in res.values()):
    run.end(CANNOT, "refused for another reason: " + json.dumps(res))
run.end(HOLDS, "control rests; both stops outside the limits refused when placed: " + json.dumps(res))
