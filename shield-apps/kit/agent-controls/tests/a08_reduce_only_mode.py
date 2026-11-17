"""A08 - the policy is reduce-only (side mode 1). The agent opens a new position. Expected: refused,
reduce_only_or_side."""
from shield import *

run = Run("A08", "agent opens a position under a reduce-only policy")
net = Net(run)
exp = now_ms() + 3600_000
s = setup_or_end(run, net, policy=default_policy(exp, side_mode=1))
eth = s["eth"]
p8 = near(net, eth)
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "20", p8), p8),
               ("reduce_only_or_side", "locked_reduce_only"), "opening order under reduce-only")
