"""A32 - the same signed agent order is sent twice, and again after the first copy was cancelled. Expected: one
order at most; a copy never places a second order."""
from shield import *

run = Run("A32", "replay of a signed agent order", extra=funded_args)
net = Net(run)
s = funded_setup(run, net)
eth = s["eth"]
before = set(resting_ids(s["owner"]))
p8 = net.px(eth, "0.94")
body = order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "15", p8), p8)
r1 = post("/order/place", body)
r2 = post("/order/place", body)
run.step("sent_twice", first=[r1["http"], r1["answer"]], second=[r2["http"], r2["answer"]])
time.sleep(6)
mine = lambda: [int(o.get("id", o.get("order_id"))) for o in orders_of(s["owner"]) if str(o.get("client_nonce")) == str(body["clientNonce"])]
new = mine()
run.step("after_twice", new=new)
for i in new:
    post("/order/cancel", cancel_body(s["agent_key"], s["owner"], i))
time.sleep(5)
r3 = post("/order/place", body)
run.step("sent_after_cancel", third=[r3["http"], r3["answer"]])
time.sleep(6)
again = mine()
run.step("after_replay", new=again)
owner_cancel_all_resting(run, s["owner_key"])
if len(new) > 1 or again:
    run.end(WORKS, f"the same signed order placed {len(new)} order(s) at once and {len(again)} after cancel")
if not new:
    run.end(CANNOT, "the first copy did not rest, so a replay could not be judged")
run.end(HOLDS, "one order from two copies; the copy after cancel placed nothing")
