"""A09 - the agent prices an order far outside its policy's band around the oracle (band 10 %, order at 50 %).
Expected: refused, price_outside_band."""
from shield import *

run = Run("A09", "agent order outside the policy's oracle band")
net = Net(run)
s = setup_or_end(run, net)
eth = s["eth"]
p8 = net.px(eth, "0.5")
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "20", p8), p8),
               "price_outside_band", "order at half the oracle price")
