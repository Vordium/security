"""B04 - server-side request forgery through tool arguments. Every argument that could reach a URL (market symbol,
pair id, address, agent, order id, transaction hash, block height, season, board, window, sort, resolution, price
kind, limit, depth) is sent with path, query, host and encoding payloads. Every request the server then makes is
recorded. Expected: every request goes to the network's own hosts, and no payload text appears in any URL."""
from mcpkit import *
from urllib.parse import urlsplit

run = Run("B04", "URL and host injection through tool arguments")
cfg = config("--owner", "0x" + "1" * 40)
rec = Recorder()
chain = make(cfg, rec)
PAY = ["../../x/y", "ETH/../../private", "ETH?x=1&y=2", "ETH#frag", "@169.254.169.254", "http://127.0.0.1:1/x",
       "ETH%2F..%2Fprivate", "ETH\r\nHost: evil", "1;rm", "0x" + "1" * 40 + "/../../private", "-1", "1e9", "99999999999999999999999",
       "0x" + "ab" * 32 + "/x", "pnl&kind=evil", "7d&limit=100000"]
TOKENS = ["private", "169.254", "127.0.0.1", "evil", "%2F", "frag", "rm", "y=2", "100000"]
tools = rpc(chain, cfg, "tools/list")["result"]["tools"]
sent = 0
for t in tools:
    if (t.get("annotations") or {}).get("destructiveHint"):
        continue
    props = list(((t.get("inputSchema") or {}).get("properties") or {}).keys())
    for k in props:
        for p in PAY:
            base = {"symbol": "ETH"} if "symbol" in props and k not in ("symbol", "pair_id") else {}
            if "address" in props and k != "address":
                base["address"] = "0x" + "1" * 40
            call_tool(chain, cfg, t["name"], {**base, k: p})
            sent += 1
hits = []
for c in rec.calls:
    u = c["url"]
    sp = urlsplit(u)
    if sp.hostname not in ("testnet.vordex.xyz", "rpc-testnet.vordium.com", "testnet.vordscan.io"):
        hits.append(("host", u))
    elif any(tok in u for tok in TOKENS) or "\r" in u or "\n" in u or "/../" in u:
        hits.append(("path", u))
run.step("summary", calls_sent=sent, requests_made=len(rec.calls), hosts=sorted({urlsplit(c["url"]).hostname for c in rec.calls}),
         injected=hits[:10])
if hits:
    run.end(WORKS, f"{len(hits)} request(s) carried argument text into a URL or another host: {hits[:3]}")
run.end(HOLDS, f"{sent} hostile arguments, {len(rec.calls)} requests: all to the network's hosts, none carrying the payload")
