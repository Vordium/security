"""B08 - the public HTTP mode's own guards, run locally in hosted mode against a stand-in network (no load on any
real server): per-connection burst then 429, a session id the server did not issue (404), JSON-RPC batches (400),
bodies over 64 KB (413), a wrong content type (415), and in plain (not hosted) HTTP mode a browser origin that was not
allowed (403, the DNS-rebinding guard). Expected: every guard answers as stated."""
from mcpkit import *
import threading, requests as rq

run = Run("B08", "HTTP mode guards: rate, sessions, batches, size, origin")


def fake(method, url, body=None, timeout=12):
    return 200, json.dumps({"chain_head": 1, "ok": True})


def serve(*argv):
    from vordium_mcp import server
    cfg = config(*argv)
    box = {}
    t = threading.Thread(target=server.serve_http, args=(cfg,), kwargs={"chain": make(cfg, fake), "ready": lambda h: box.setdefault("h", h), "env": {}}, daemon=True)
    t.start()
    for _ in range(100):
        if "h" in box:
            break
        time.sleep(0.05)
    h = box["h"]
    return h, f"http://127.0.0.1:{h.server_address[1]}/mcp"


H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
h, url = serve("--http", "127.0.0.1:0", "--hosted")
init = rq.post(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "c", "version": "1"}}}), headers=H, timeout=10)
sid = init.headers.get("Mcp-Session-Id")
codes = []
for i in range(30):
    r = rq.post(url, data=json.dumps({"jsonrpc": "2.0", "id": i + 2, "method": "tools/call", "params": {"name": "get_status", "arguments": {}}}),
                headers={**H, "Mcp-Session-Id": sid}, timeout=10)
    codes.append(r.status_code)
first429 = codes.index(429) + 1 if 429 in codes else None
forged = rq.post(url, data=json.dumps({"jsonrpc": "2.0", "id": 99, "method": "tools/list"}), headers={**H, "Mcp-Session-Id": "f" * 32}, timeout=10).status_code
batch = rq.post(url, data=json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}] * 3), headers=H, timeout=10).status_code
big = rq.post(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"x": "a" * 70000}}), headers=H, timeout=10).status_code
ctype = rq.post(url, data="{}", headers={"Content-Type": "text/plain"}, timeout=10).status_code
h.shutdown()
h2, url2 = serve("--http", "127.0.0.1:0")
origin = rq.post(url2, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}), headers={**H, "Origin": "http://rebind.example"}, timeout=10).status_code
noorigin = rq.post(url2, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}), headers=H, timeout=10).status_code
h2.shutdown()
got = {"burst_then_429_at": first429, "statuses": codes, "forged_session": forged, "batch": batch, "over_64kb": big,
       "wrong_content_type": ctype, "foreign_origin_plain_mode": origin, "no_origin_plain_mode": noorigin}
run.step("answers", **got)
want = {"forged_session": 404, "batch": 400, "over_64kb": 413, "wrong_content_type": 415, "foreign_origin_plain_mode": 403}
wrong = {k: got[k] for k, v in want.items() if got[k] != v}
if first429 is None or first429 > 21:
    wrong["burst"] = first429
if wrong:
    run.end(WORKS, "a guard did not answer as stated: " + json.dumps(wrong))
run.end(HOLDS, f"429 after {first429 - 1} calls in one connection; forged session 404; batch 400; 64 KB+ 413; content type 415; foreign origin 403")
