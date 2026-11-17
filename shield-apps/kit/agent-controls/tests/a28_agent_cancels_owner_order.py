"""A28 - an agent cancels an order its owner placed (the chain's rule: an agent cancels only its own orders).
Funded owner. Expected: refused (not_agents_order); the owner's order still rests."""
from shield import *

run = Run("A28", "agent cancels its owner's order", extra=funded_args)
net = Net(run)
s = funded_setup(run, net)
fate = owner_rests(run, net, s)
oid = int(fate["order_id"])
r = post("/order/cancel", cancel_body(s["agent_key"], s["owner"], oid))
run.step("attack", http=r["http"], answer=r["answer"])
time.sleep(6)
still = oid in resting_ids(s["owner"])
evs = [e for e in agent_events(s["agent"], 20) if e.get("kind") == "agent_refused"][:3]
run.step("after", owner_order_rests=still, agent_refusals=evs)
owner_cancel_all_resting(run, s["owner_key"])
if still:
    run.end(HOLDS, f"the owner's order still rests (intake {r['http']} {(r['answer'] or {}).get('reason') or (r['answer'] or {}).get('code')})")
run.end(WORKS, "an agent cancelled an order its owner placed")
