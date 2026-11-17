"""A05 - the owner disables the policy; the agent still orders. Expected: refused, policy_disabled."""
from shield import *

run = Run("A05", "agent order while the owner has disabled its policy")
net = Net(run)
exp = now_ms() + 3600_000
s = setup_or_end(run, net, policy=default_policy(exp, enabled=False))
eth = s["eth"]
p8 = near(net, eth)
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "20", p8), p8),
               "policy_disabled", "order with the policy disabled")
