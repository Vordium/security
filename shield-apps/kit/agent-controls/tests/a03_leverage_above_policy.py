"""A03 - an agent orders at a leverage above its policy (5x). Expected: refused, max_leverage."""
from shield import *

run = Run("A03", "agent order above the policy's leverage")
net = Net(run)
s = setup_or_end(run, net)
eth = s["eth"]
p8 = near(net, eth)
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "20", p8), p8,
                                  leverage_bps=10 * 10000), "max_leverage", "order at 10x (policy 5x)")
