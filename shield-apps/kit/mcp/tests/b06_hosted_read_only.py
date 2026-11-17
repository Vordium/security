"""B06 - the hosted server is read-only. One connection that declares every client capability (elicitation, sampling,
roots) lists the tools and tries to force writes: place_order, stop_all and cancel_all, and the local-only check_order,
then a resource outside the list. Expected: no tool that signs or reads a configured account is listed; each forced
call is refused as an unknown tool; health says read_only. Eight requests in all."""
from mcpkit import *
import requests as rq

run = Run("B06", "the hosted server cannot be made to write")
health = rq.get(HOSTED.rsplit("/mcp", 1)[0] + "/health", timeout=15).json()
run.step("health", read_only=health.get("read_only"), version=health.get("version"), network=health.get("network"))
h = Hosted()
c, init = h.open({"elicitation": {"form": {}}, "sampling": {}, "roots": {"listChanged": True}})
c, lst = h.send("tools/list")
tools = [t["name"] for t in (lst.get("result") or {}).get("tools") or []]
destructive = [t["name"] for t in (lst.get("result") or {}).get("tools") or [] if (t.get("annotations") or {}).get("readOnlyHint") is False
               or (t.get("annotations") or {}).get("destructiveHint")]
run.step("tools", count=len(tools), names=tools, not_read_only=destructive, instructions=(init.get("result") or {}).get("instructions"))
forced = {}
for name in ("place_order", "stop_all", "cancel_all", "check_order"):
    c, j = h.send("tools/call", {"name": name, "arguments": {"symbol": "ETH", "side": "buy", "size": 1}})
    r = j.get("result") or {}
    forced[name] = {"http": c, "isError": r.get("isError"), "reason": (r.get("structuredContent") or {}).get("reason")}
c, j = h.send("resources/read", {"uri": "file:///etc/passwd"})
forced["resource_file"] = {"http": c, "error": (j.get("error") or {}).get("message")}
run.step("forced", **forced)
WRITES = {"place_order", "close_position", "set_tpsl", "modify_order", "cancel_order", "cancel_all", "stop_all", "check_order", "my_buying_power"}
problems = []
if health.get("read_only") is not True:
    problems.append("health does not say read_only")
if set(tools) & WRITES or destructive:
    problems.append(f"write or account tools listed: {sorted(set(tools) & WRITES) + destructive}")
for n in ("place_order", "stop_all", "cancel_all", "check_order"):
    if forced[n]["isError"] is not True or "no tool named" not in str(forced[n]["reason"]):
        problems.append(f"{n} was not refused as unknown")
if "error" not in j:
    problems.append("an unlisted resource was served")
if not tools:
    run.end(CANNOT, "the hosted server did not list its tools")
if problems:
    run.end(WORKS, "; ".join(problems))
run.end(HOLDS, f"{len(tools)} read tools only; forced writes refused as unknown tools; health read_only true")
