"""B12 - automatic orders (--orders auto). With auto on, orders inside the agent's on-chain limits are signed without
asking; that is the user's choice. Everything outside them must still stop before a signature: an order on a market the
agent may not trade, one above its largest order, one above its leverage, a market that is paused or unknown. The server
runs with the funded owner's agent behind a local relay that holds every write. Expected: none of the out-of-limit
orders is signed (no write reaches the relay); the in-limit order is signed without a question (by design)."""
from mcpkit import *

run = Run("B12", "automatic orders stay inside the agent's limits", extra=trading_args)
shield, net, s = trading_agent(run)
relay = Relay()
kp = agent_key_path(run, s)
cfg = config("--allow-trading", "--owner", s["owner"], "--agent-key-file", kp, "--orders", "auto", "--rest", relay.url)
chain = make(cfg, None)
asker = Asker(elicit=True, answer={"action": "accept", "content": {"confirm": True}})
eth = s["eth"]
o8 = net.oracle8(eth["pairId"]) / 1e8
lot = int(eth["lot18dec"]) / 1e18
CASES = [("not_allowed_market", {"symbol": "BTC", "side": "buy", "size": 0.001, "order_type": "limit", "price": round(net.oracle8(net.pair("BTC")["pairId"]) / 1e8 * 0.95, 0)}),
         ("above_largest_order", {"symbol": "ETH", "side": "buy", "size": round(lot * 1000 * 3, 6), "order_type": "limit", "price": round(o8 * 0.95, 1)}),
         ("above_leverage", {"symbol": "ETH", "side": "buy", "size": round(lot * 100, 6), "order_type": "limit", "price": round(o8 * 0.95, 1), "leverage": 20}),
         # worth about 20 USD at half the price: above the smallest order, inside the largest, so only the band can refuse it
         ("outside_band", {"symbol": "ETH", "side": "buy", "size": round(max(lot * 100, (20 / (o8 * 0.5)) // lot * lot + lot), 6), "order_type": "limit", "price": round(o8 * 0.5, 1)}),
         ("unknown_market", {"symbol": "NOPE", "side": "buy", "size": 1, "order_type": "market"})]
signed = []
for label, args in CASES:
    n0 = len(relay.posts)
    res = call_tool(chain, cfg, "place_order", args, session=asker)
    st = res["structured"] or {}
    run.step("case", label=label, refused=res["is_error"], reason=str(st.get("reason"))[:240], writes=len(relay.posts) - n0)
    if label == "outside_band" and res["is_error"] and ("smallest order" in str(st.get("reason")) or "price within" not in str(st.get("reason"))):
        run.end(CANNOT, "the outside-band case was refused for another reason as well, so the band rule is not shown alone: " + str(st.get("reason"))[:200])
    if len(relay.posts) > n0:
        signed.append(label)
n0 = len(relay.posts)
inside = {"symbol": "ETH", "side": "buy", "size": round(lot * 100, 6), "order_type": "limit", "price": round(o8 * 0.95, 1), "leverage": 2}
res = call_tool(chain, cfg, "place_order", inside, session=asker)
run.step("in_limits_by_design", refused=res["is_error"], reason=str((res["structured"] or {}).get("reason"))[:200],
         writes=len(relay.posts) - n0, asked=len(asker.asked))
relay.close()
if len(relay.posts) == n0:
    run.end(CANNOT, "the positive control (an order inside every limit) was not signed, so a server that signs nothing "
                    "would pass: " + str((res["structured"] or {}).get("reason"))[:120])
if asker.asked:
    run.end(WORKS, f"automatic mode asked the user {len(asker.asked)} time(s): it is not the automatic mode it says")
if signed:
    run.end(WORKS, "auto mode signed an order outside the agent's limits: " + ", ".join(signed))
run.end(HOLDS, f"{len(CASES)} out-of-limit orders stopped before any signature; the in-limit control was signed without a question")
