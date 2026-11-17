"""A06 - the policy allows trading only in a window that excludes now. Expected: refused, outside_active_window."""
from shield import *

run = Run("A06", "agent order outside the policy's active hours")
net = Net(run)
day = now_ms() % 86_400_000
start = (day + 6 * 3600_000) % 86_400_000                 # a one-hour window six hours from now (UTC)
exp = now_ms() + 3600_000
s = setup_or_end(run, net, policy=default_policy(exp, active_from_ms_of_day=start,
                                                 active_to_ms_of_day=(start + 3600_000) % 86_400_000))
eth = s["eth"]
p8 = near(net, eth)
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "20", p8), p8),
               "outside_active_window", "order outside the active hours")
