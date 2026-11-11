#!/usr/bin/env python3
"""Read the hosted Vordium AI server's public health answer on both networks.

  python3 verifiers/check_hosted_ai_server.py [--json]

For mainnet and testnet it reads https://mcp.vordium.com/<network>/health and checks:
  - "ok" is true and "network" names the network asked for;
  - "read_only" is true (the hosted server never signs);
  - per-client request limits are published ("limits" with per_minute and burst above zero);
  - "version" is present, so you can match it with the published vordium-mcp release.
Uses only the Python standard library. Exit 0 = both pass, 1 = a check fails, 2 = the server could not be reached.
"""
import json
import sys
import urllib.request

BASE = "https://mcp.vordium.com/{}/health"


def check(net: str) -> dict:
    url = BASE.format(net)
    req = urllib.request.Request(url, headers={"User-Agent": "vordium-security-verifier/1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — reported, never hidden
        return {"network": net, "reached": False, "error": f"{type(e).__name__}: {e}"}
    lim = body.get("limits") or {}
    problems = []
    if body.get("ok") is not True:
        problems.append("ok is not true")
    if body.get("network") != net:
        problems.append(f"network is {body.get('network')!r}")
    if body.get("read_only") is not True:
        problems.append("read_only is not true")
    if not (isinstance(lim.get("per_minute"), int) and lim["per_minute"] > 0
            and isinstance(lim.get("burst"), int) and lim["burst"] > 0):
        problems.append("request limits are not published")
    if not body.get("version"):
        problems.append("no version")
    return {"network": net, "reached": True, "version": body.get("version"), "read_only": body.get("read_only"),
            "limits": lim, "pass": not problems, "problems": problems}


def main() -> int:
    results = [check(n) for n in ("mainnet", "testnet")]
    if "--json" in sys.argv[1:]:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            if not r["reached"]:
                print(f"UNREACHABLE  {r['network']}  {r['error']}")
            else:
                print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['network']}  version {r['version']}  "
                      f"read_only={r['read_only']}  limits={json.dumps(r['limits'])}"
                      + ("" if r["pass"] else "  — " + "; ".join(r["problems"])))
    if any(not r["reached"] for r in results):
        return 2
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
