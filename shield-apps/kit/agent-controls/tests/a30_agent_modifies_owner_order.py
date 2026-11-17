"""A30 - an agent modifies (cancel-and-replace) an order its owner placed: moving it across the book would fill it at
a bad price. Expected: refused (not_agents_order); the owner's order is unchanged."""
from shield import *
from vordium import mm

run = Run("A30", "agent modifies its owner's order", extra=funded_args)
net = Net(run)
s = funded_setup(run, net)
fate = owner_rests(run, net, s)
oid = int(fate["order_id"])
before = [o for o in orders_of(s["owner"]) if int(o.get("id", o.get("order_id"))) == oid]
eth = s["eth"]
np8 = net.px(eth, "0.95")
n = now_ms()
sig = mm.sign(s["agent_key"], mm.digest(mm.modify_v2_struct_hash(s["owner"], oid, np8, int(eth["lot18dec"]) * 100, n),
                                       separator("VordCore")))
r = post("/order/modify", mm.modify_body(s["owner"], oid, np8, int(eth["lot18dec"]) * 100, n, sig))
run.step("attack", http=r["http"], answer=r["answer"])
time.sleep(6)
after = [o for o in orders_of(s["owner"]) if int(o.get("id", o.get("order_id"))) == oid]
run.step("after", before=before, after=after)
owner_cancel_all_resting(run, s["owner_key"])
if after and after == before:
    run.end(HOLDS, f"the owner's order is unchanged (intake {r['http']} {(r['answer'] or {}).get('code')})")
run.end(WORKS, "an agent changed an order its owner placed")
