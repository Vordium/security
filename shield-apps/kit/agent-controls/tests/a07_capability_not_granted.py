"""A07 - the policy grants cancel and close only (no place). The agent places an order. Expected: refused,
capability_not_granted."""
from shield import *

run = Run("A07", "agent places an order without the place capability")
net = Net(run)
exp = now_ms() + 3600_000
s = setup_or_end(run, net, policy=default_policy(exp, caps_bitmask=0b010010))
eth = s["eth"]
p8 = near(net, eth)
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "20", p8), p8),
               "capability_not_granted", "place without the place capability")
