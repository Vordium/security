"""A02 - an agent orders more than the market limit's largest order. Expected: refused, max_order."""
from shield import *

run = Run("A02", "agent order above the largest order the owner placed")
net = Net(run)
s = setup_or_end(run, net)
eth = s["eth"]
p8 = near(net, eth)
mo = int(eth["lot18dec"]) * 1000                      # the largest order setup_agent sets
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, mo * 2, p8),
               ("max_order", "order_notional_above_agent_max"), "order of twice the largest order")
