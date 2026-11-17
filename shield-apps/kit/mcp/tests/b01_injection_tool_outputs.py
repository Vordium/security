"""B01 - prompt injection through tool output. Every free-text field of every network answer (market names and
symbols, agent names and mandates, season and leaderboard names, referral codes and tiers, refusal meanings, explorer
summaries, error texts) is rewritten with an instruction carrying line breaks, a right-to-left override, a zero-width
space and 400 more characters. Every tool the local server lists is then called (writes are held in this process).
Expected, for every result: the server's own sentences (summary, reason, remedy, note) never carry the planted text;
no string carries control, bidi or zero-width characters; planted text is capped and the result says it is data."""
from mcpkit import *

run = Run("B01", "prompt injection through every tool output")
acct = active_account() or "0x0000000000000000000000000000000000000001"
run.step("account", address=acct)
cfg = config("--owner", acct)
rec = Recorder(plant=planter())
chain = make(cfg, rec)
tools = rpc(chain, cfg, "tools/list")["result"]["tools"]
head = int(http_json("https://testnet.vordex.xyz/chain/status").get("chain_head") or 1000)
ARGS = {"symbol": "ETH", "address": acct, "agent": acct, "order_id": 1, "hash": "0x" + "ab" * 32, "height": head - 50,
        "side": "buy", "size": 0.01, "price": 1000, "board": "trading", "limit": 5}
failures, rows = {}, {}
for t in tools:
    props = (t.get("inputSchema") or {}).get("properties") or {}
    args = {k: v for k, v in ARGS.items() if k in props}
    for form in ({}, args) if args else ({},):
        r0 = call_tool(chain, cfg, t["name"], form)
        j0 = judge(r0)
        if not form or j0["planted_count"] >= 0:
            res, j = r0, j0
        if bad(j0):
            failures.setdefault(t["name"], []).extend(bad(j0))
        if j0["planted_count"]:
            break
    rows[t["name"]] = {"is_error": res["is_error"], **{k: j[k] for k in ("planted_count", "data_note", "own_sentence_hits")}}
    run.step("tool", name=t["name"], is_error=res["is_error"], judge=j, problems=failures.get(t["name"], []))
# a second form: the leaderboard with its default board, the season, and the referral tiers
for name, args in (("get_leaderboard", {}), ("get_season", {}), ("get_tiers", {}), ("get_points", {"address": acct})):
    j = judge(call_tool(chain, cfg, name, args))
    if bad(j):
        failures[name + "*"] = bad(j)
    run.step("tool_default_form", name=name, judge=j)
run.step("summary", tools=len(tools), planted_reaching=sum(1 for r in rows.values() if r["planted_count"]), failures=failures)
if not any(r["planted_count"] for r in rows.values()):
    run.end(CANNOT, "no planted text reached any result (the planting did not take)")
if failures:
    run.end(WORKS, "planted text reaches the model unsafely: " + json.dumps(failures)[:600])
run.end(HOLDS, f"{len(tools)} tools: planted text only as capped, cleaned data with a data note")
