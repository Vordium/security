"""A27 - an agent of owner A signs an order with owner = B (an account that never registered it). Expected: refused,
bad signature (the key is not a live signer of B)."""
from shield import *

run = Run("A27", "agent orders for an account that is not its owner")
net = Net(run)
s = setup_or_end(run, net)
b = addr(new_key(run, "victim"))
eth = s["eth"]
p8 = near(net, eth)
body = order_body(s["agent_key"], b, eth["pairId"], 0, net.size18(eth, "20", p8), p8)
r = post("/order/place", body)
fate = order_fate(b, s["agent"], body["clientNonce"], r, 8)
run.step("attack", http=r["http"], answer=r["answer"], fate=fate)
if fate["outcome"].startswith("accepted"):
    run.end(WORKS, "the chain took an order for an account the agent does not belong to")
code = (r["answer"] or {}).get("code") if isinstance(r["answer"], dict) else None
run.end(HOLDS, f"refused ({r['http']} {code})")
