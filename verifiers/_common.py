"""Shared helpers for the Vordium verifiers: one JSON GET / POST with a plain client name and a time limit. Standard library only."""
import json
import urllib.error
import urllib.request

UA = {"user-agent": "vordium-verify/1", "content-type": "application/json"}
TESTNET_NODE = "https://testnet.vordex.xyz/chain"
TESTNET_ARCHIVE = "https://testnet.vordex.xyz/chain-archive"
MAINNET_NODE = "https://rpc.vordium.com"
ARBITRUM_SEPOLIA_RPC = "https://sepolia-rollup.arbitrum.io/rpc"
ARBITRUM_ONE_RPC = "https://arb1.arbitrum.io/rpc"


def get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def get_raw(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def get_status(url, timeout=30):
    """(http status, parsed json or None) — for answers whose 404 body carries meaning"""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, None


def rpc(url, method, params, timeout=30):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, body, UA), timeout=timeout) as r:
        d = json.load(r)
    if "error" in d:
        raise RuntimeError(d["error"])
    return d["result"]
