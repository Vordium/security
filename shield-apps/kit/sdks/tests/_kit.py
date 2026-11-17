"""Shared helpers for the SDK re-run kit (Python side).

Self-contained: standard library + the published `vordium` package (pip install vordium).
Every test exits 0 = the defence holds, 1 = the attack works (or the requirement fails), 3 = cannot run.
Throwaway keys are made in memory and never printed or written.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PASS, FAIL, CANNOT = 0, 1, 3

MAINNET_GENESIS = "2c1c0679fa6ab8358f1d3e8d294a8d1c73ac2e2caf9079f1216abedc3d9fdf4f"
TESTNET_GENESIS = "8b5d414c5cd5d18bc468b64f87ac8e2c2b5ff494c769d5e09dcf50ce75a59792"
TESTNET_API = "https://testnet.vordex.xyz/chain"


class Results:
    """Collects one line per check and turns them into the exit code."""

    def __init__(self, title: str):
        self.title, self.rows, self.cannot = title, [], []
        print("=" * 78)
        print(title)
        print("=" * 78)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok)))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
        return ok

    def skip(self, name: str, why: str) -> None:
        self.cannot.append(name)
        print(f"[CANNOT RUN] {name} -- {why}")

    def finish(self) -> None:
        fails = [n for n, ok in self.rows if not ok]
        passed = len(self.rows) - len(fails)
        print("-" * 78)
        print(f"checks: {passed} pass, {len(fails)} fail, {len(self.cannot)} cannot run")
        if fails:
            print("RESULT: ATTACK WORKS / REQUIREMENT FAILS (exit 1): " + "; ".join(fails))
            sys.exit(FAIL)
        if not self.rows:
            print("RESULT: CANNOT RUN (exit 3)")
            sys.exit(CANNOT)
        print("RESULT: DEFENDED (exit 0)")
        sys.exit(PASS)


def get_json(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "vordium-rerun-kit"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class Stub:
    """A local read-and-write service on 127.0.0.1 that answers what a test configures and records every request.

    routes: (METHOD, path) -> body | (status, body) | callable(handler, raw_body) -> (status, body) | ("sleep", s, status, body)
    rpc: JSON-RPC method -> result (answered on POST / and /rpc)."""

    def __init__(self):
        self.routes, self.rpc, self.log = {}, {}, []
        self._srv = None

    @property
    def base(self) -> str:
        h, p = self._srv.server_address
        return f"http://{h}:{p}"

    def start(self):
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, payload, raw=False):
                body = payload if raw else json.dumps(payload).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _route(self, method):
                path = self.path.split("?", 1)[0]
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                stub.log.append({"method": method, "path": path, "raw": raw, "t": time.time()})
                if method == "POST" and path in ("/", "/rpc"):
                    try:
                        m = json.loads(raw).get("method")
                    except Exception:
                        m = None
                    if m in stub.rpc:
                        res = stub.rpc[m]
                        return self._send(200, {"jsonrpc": "2.0", "id": 1, "result": res() if callable(res) else res})
                    return self._send(200, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "no method"}})
                r = stub.routes.get((method, path))
                if r is None:
                    return self._send(404, {"error": "not found"})
                if callable(r):
                    r = r(self, raw)
                if isinstance(r, tuple) and r and r[0] == "sleep":
                    time.sleep(r[1])
                    r = (r[2], r[3])
                if isinstance(r, tuple) and r and r[0] == "redirect":
                    self.send_response(r[1])
                    self.send_header("Location", r[2] + self.path)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "22")
                    self.end_headers()
                    self.wfile.write(b'{"status":"submitted"}')
                    return None
                if isinstance(r, tuple) and r and r[0] == "raw":
                    return self._send(r[1], r[2], raw=True)
                if isinstance(r, tuple):
                    return self._send(r[0], r[1])
                return self._send(200, r)

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()

    def identity(self, chain_id, genesis, rpc_chain_id=None, spec_extra=None, testnet=True):
        """Serve one network identity: /status, /network-spec.json and eth_chainId."""
        self.routes[("GET", "/status")] = {"chain_id": chain_id, "genesis_sha256": genesis}
        spec = {"chainId": chain_id, "genesisSha256": genesis, "testnet": testnet, "rpc": None}
        spec.update(spec_extra or {})
        self.routes[("GET", "/network-spec.json")] = spec
        cid = chain_id if rpc_chain_id is None else rpc_chain_id
        self.rpc["eth_chainId"] = cid if isinstance(cid, str) else hex(int(cid))
        return self


def clean_env():
    import os
    for k in ("VORDIUM_CHAIN_ID", "VORDIUM_GENESIS_SHA256", "VORDIUM_RPC_URL", "VORDIUM_NETWORK", "VORDIUM_SPEC_URL"):
        os.environ.pop(k, None)


def live_specs():
    """The test network's market rules (a public GET), or None when it cannot be read."""
    try:
        return get_json(TESTNET_API + "/markets/specs")
    except Exception:
        return None
