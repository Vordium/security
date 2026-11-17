"""A33 - nonce games: an agent signs an order with a client nonce 30 days ahead (to burn its window, or the owner's).
Expected: refused; afterwards the agent's and the owner's normal orders are still taken."""
from shield import *

run = Run("A33", "agent order with a far-future nonce", extra=funded_args)
net = Net(run)
s = funded_setup(run, net)
eth = s["eth"]
p8 = net.px(eth, "0.94")
sz = net.size18(eth, "15", p8)
far = order_body(s["agent_key"], s["owner"], eth["pairId"], 0, sz, p8, client_nonce=now_ms() + 30 * 86_400_000)
r = post("/order/place", far)
f0 = order_fate(s["owner"], s["agent"], far["clientNonce"], r, 8)
run.step("far_nonce", http=r["http"], answer=r["answer"], fate={k: v for k, v in f0.items() if k != "order"})
a = order_body(s["agent_key"], s["owner"], eth["pairId"], 0, sz, p8, client_nonce=now_ms())
fa = order_fate(s["owner"], s["agent"], a["clientNonce"], post("/order/place", a), 10)
o = order_body(s["owner_key"], s["owner"], eth["pairId"], 0, sz, net.px(eth, "0.93"), client_nonce=now_ms() + 1)
fo = order_fate(s["owner"], s["owner"], o["clientNonce"], post("/order/place", o), 10)
run.step("after", agent_normal=fa["outcome"], owner_normal=fo["outcome"])
owner_cancel_all_resting(run, s["owner_key"])
if f0["outcome"].startswith("accepted"):
    run.end(WORKS, "an order 30 days ahead was taken")
if not (fa["outcome"].startswith("accepted") and fo["outcome"].startswith("accepted")):
    run.end(WORKS, f"after the far-future nonce a normal order was refused (agent {fa['outcome']}, owner {fo['outcome']})")
run.end(HOLDS, "the far-future nonce was refused and normal orders still go through")
