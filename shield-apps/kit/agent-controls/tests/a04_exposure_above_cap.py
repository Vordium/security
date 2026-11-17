"""A04 - an agent orders past its total exposure cap. The owner sets the cap to 15 USDC and allows a larger single
order, so only the exposure cap can refuse it. Expected: refused, max_total_exposure."""
from shield import *

run = Run("A04", "agent order above the total exposure cap")
net = Net(run)
exp = now_ms() + 3600_000
s = setup_or_end(run, net, policy=default_policy(exp, max_total_exposure_6dec=15 * E6))
eth = s["eth"]
p8 = near(net, eth)
size = net.size18(eth, "60", p8)
if size > int(eth["lot18dec"]) * 1000:
    run.end(CANNOT, "60 USDC of ETH is above the largest order setup allows; raise it")
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, size, p8),
               ("max_total_exposure", "order_notional_above_agent_max"), "order of 60 USDC (exposure cap 15 USDC)")
