"""A12 - an agent signs SetAgentMarketLimit for itself to allow a second market (BTC) with a huge largest order.
Expected: the stored market limits do not change."""
from shield import *

run = Run("A12", "agent widens its own market limits")
net = Net(run)
s = setup_or_end(run, net)
btc = net.pair("BTC")
owner, agent = s["owner"], s["agent"]
read = lambda: sorted((m.get("pair"), m.get("allowed"), str(m.get("max_order_18dec"))) for m in market_rows(agent_rec(owner, agent)))
before = read()
for pair, label in ((btc, "new_market"), (s["eth"], "raise_existing")):
    r = submit(signed_op(s["agent_key"], "SetAgentMarketLimit", {
        "owner": owner, "agent": agent, "pair": int(pair["pairId"]), "allowed": True, "maxOrder18dec": 10 ** 24,
        "maxPosition18dec": 10 ** 25, "maxLeverageBps": 50 * 10000, "nonce": NONCE()}))
    run.step("sent_" + label, http=r["http"], answer=r["answer"])
if unchanged(run, "market_limits", read, before, 15):
    run.end(HOLDS, "the agent-signed market limits were not applied")
run.end(WORKS, "the chain applied a market limit the agent signed for itself")
