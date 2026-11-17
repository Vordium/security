"""A01 - an agent orders on a market its policy does not allow. Expected: refused, market_not_allowed."""
from shield import *

run = Run("A01", "agent order on a market the policy does not allow")
net = Net(run)
s = setup_or_end(run, net)
btc = net.pair("BTC")
p8 = near(net, btc)
expect_refusal(run, s, order_body(s["agent_key"], s["owner"], btc["pairId"], 0, net.size18(btc, "20", p8), p8),
               "market_not_allowed", "order on BTC (only ETH allowed)")
