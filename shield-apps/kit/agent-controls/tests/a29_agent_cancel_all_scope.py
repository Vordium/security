"""A29 - an agent sends cancel-all for its owner's account (on the ETH market). Expected: only the agent's own orders go; the owner's
order still rests."""
from shield import *
from vordium import mm

run = Run("A29", "agent cancel-all reaches its owner's orders", extra=funded_args)
net = Net(run)
s = funded_setup(run, net)
fate = owner_rests(run, net, s)
oid = int(fate["order_id"])
eth = s["eth"]
p8 = net.px(eth, "0.94")
ab = order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "15", p8), p8)
ar = post("/order/place", ab)
af = order_fate(s["owner"], s["agent"], ab["clientNonce"], ar, 10)
run.step("agent_order", fate={k: v for k, v in af.items() if k != "order"})
n = NONCE()
sig = mm.sign(s["agent_key"], mm.digest(mm.cancel_all_struct_hash(s["owner"], eth["pairId"], n), separator("VordCore")))
r = post("/order/cancel-all", mm.cancel_all_body(s["owner"], eth["pairId"], n, sig))
run.step("attack", http=r["http"], answer=r["answer"])
time.sleep(6)
ids = resting_ids(s["owner"])
run.step("after", resting=ids, owner_order=oid, agent_order=af.get("order_id"))
owner_cancel_all_resting(run, s["owner_key"])
if oid in ids:
    run.end(HOLDS, "the owner's order survived the agent's cancel-all")
run.end(WORKS, "an agent's cancel-all cancelled an order its owner placed")
