"""B07 - tool-schema poisoning. A client trusts the tool names, descriptions and schemas it is given. They must be the
published ones: the installed package's tool list must equal its own lock file (tools.lock.json, shipped in the
package's source), must not change when the network's answers carry planted text, and the hosted server must list
exactly the published read tools with the same descriptions and schemas. Expected: all three equal."""
from mcpkit import *
import hashlib, urllib.request

run = Run("B07", "tool descriptions and schemas are the published ones")
ver = run.version


def canon(tools):
    keep = ("name", "title", "description", "inputSchema", "outputSchema", "annotations")
    return {t["name"]: hashlib.sha256(json.dumps({k: t.get(k) for k in keep}, sort_keys=True).encode()).hexdigest()
            for t in tools}


cfg_local = config()
cfg_ro = config("--http", "127.0.0.1:0")
clean_list = rpc(make(cfg_local, None), cfg_local, "tools/list")["result"]["tools"]
planted_list = rpc(make(cfg_local, Recorder(plant=planter())), cfg_local, "tools/list")["result"]["tools"]
ro_list = rpc(make(cfg_ro, None), cfg_ro, "tools/list")["result"]["tools"]
lock = None
try:
    url = f"https://raw.githubusercontent.com/Vordium/Vordium-MCP/v{ver}/tools.lock.json"
    with urllib.request.urlopen(url, timeout=15) as r:
        lock = json.loads(r.read().decode())
except Exception as e:
    run.step("lock_unreadable", error=type(e).__name__)
h = Hosted()
h.open()
c, j = h.send("tools/list")
hosted = (j.get("result") or {}).get("tools") or []
a, b, ro, ho = canon(clean_list), canon(planted_list), canon(ro_list), canon(hosted)
diff_planted = sorted(k for k in a if a.get(k) != b.get(k))
diff_hosted = sorted(set(ro) ^ set(ho)) + sorted(k for k in ro if k in ho and ro[k] != ho[k])
diff_lock = None
if isinstance(lock, dict):
    lk = canon(lock.get("tools") or [])
    diff_lock = sorted(set(lk) ^ set(a)) + sorted(k for k in a if k in lk and lk[k] != a[k])
run.step("compare", installed=len(a), hosted=len(ho), changed_by_planting=diff_planted, hosted_vs_published_read_tools=diff_hosted,
         installed_vs_lock=diff_lock)
if diff_planted or diff_hosted or diff_lock:
    run.end(WORKS, f"tool definitions differ: planting {diff_planted}, hosted {diff_hosted[:5]}, lock {diff_lock and diff_lock[:5]}")
if diff_lock is None:
    run.end(HOLDS, "planting does not change the tools; the hosted list equals the published read tools (lock file not read)")
run.end(HOLDS, "installed tools equal the published lock; planting changes nothing; hosted equals the published read tools")
