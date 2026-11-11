#!/usr/bin/env python3
"""Check that every official Vordium site tells browsers to use only secure connections.

  python3 verifiers/check_site_headers.py [--json]

For each site it requests the home page over HTTPS and reads the response headers:
  - Strict-Transport-Security must be present with max-age of at least one year (31536000 s);
  - X-Content-Type-Options is reported ("nosniff" or not) for information; it does not decide the result;
  - the address must be served over HTTPS without a certificate error.
Uses only the Python standard library and public addresses. Exit 0 = every site passes, 1 = a site fails,
2 = a site could not be reached.
"""
import json
import re
import ssl
import sys
import urllib.error
import urllib.request

SITES = [
    "https://vordium.com/",
    "https://docs.vordium.com/",
    "https://vordium.org/",
    "https://vordex.xyz/",
    "https://app.vordex.xyz/",
    "https://status.vordex.xyz/",
    "https://testnet.vordex.xyz/",
    "https://rpc.vordium.com/status",
    "https://mcp.vordium.com/mainnet/health",
]
ONE_YEAR = 31536000


def check(url: str) -> dict:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "vordium-security-verifier/1"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            h, code = r.headers, r.status
    except urllib.error.HTTPError as e:
        h, code = e.headers, e.code
    except Exception as e:  # noqa: BLE001 — any failure to reach the site is reported, never hidden
        return {"site": url, "reached": False, "error": f"{type(e).__name__}: {e}"}
    hsts = h.get("Strict-Transport-Security") or ""
    m = re.search(r"max-age=(\d+)", hsts)
    max_age = int(m.group(1)) if m else 0
    nosniff = (h.get("X-Content-Type-Options") or "").strip().lower() == "nosniff"
    problems = []
    if max_age < ONE_YEAR:
        problems.append(f"Strict-Transport-Security max-age {max_age} (needs >= {ONE_YEAR})")
    return {"site": url, "reached": True, "http_status": code, "hsts": hsts or None,
            "nosniff": nosniff, "pass": not problems, "problems": problems}


def main() -> int:
    as_json = "--json" in sys.argv[1:]
    results = [check(u) for u in SITES]
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            if not r["reached"]:
                print(f"UNREACHABLE  {r['site']}  {r['error']}")
            else:
                print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['site']}  {r['hsts'] or 'no HSTS'}  nosniff={r['nosniff']}"
                      + ("" if r["pass"] else "  — " + "; ".join(r["problems"])))
    if any(not r["reached"] for r in results):
        return 2
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
