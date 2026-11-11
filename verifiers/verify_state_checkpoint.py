#!/usr/bin/env python3
"""Vordium: check a public state-sync checkpoint against the chain, from public endpoints only.

Author: Vordium. License: Apache-2.0.

USAGE
    python3 verify_state_checkpoint.py [--files URL] [--chain URL] [--rpc URL]
                                       [--verifier PATH --genesis PATH] [--keep DIR]

    Defaults (test network):
      --files  https://rpc-testnet.vordium.com/state-sync/testnet   (latest.json, checkpoint-N.json, state-N.vsnap)
      --chain  https://testnet.vordex.xyz/chain                       (GET /registry/set, GET /batch/{n})
      --rpc    https://testnet.vordex.xyz/chain/native                (JSON-RPC eth_getBlockByNumber)

REQUIREMENTS
    Python 3.8+, standard library, plus ONE keccak-256 source: pycryptodome (`pip install pycryptodome`)
    or eth-hash (`pip install "eth-hash[pycryptodome]"`). secp256k1 signature checks are done in pure Python.

WHAT IT CHECKS (in order, each printed PASS / FAIL)
    1. file      the snapshot's byte length and sha256 equal the checkpoint's `state_len` / `state_sha256`.
    2. envelope  the snapshot starts with the 16-byte header: ASCII "VORDSNAP", schema 3, reserved 0.
    3. quorum    each attestation is a validator's signed statement "state at batch B has root R":
                 digest = keccak256(0x07 || u64 big-endian B || validator address (20) || R (32)),
                 64-byte secp256k1 signature (r || s, low-S) checked against that validator's published
                 compressed hot key, whose derived address must equal the validator. Valid, distinct attesters
                 from the currently seated set must reach a quorum: n - floor((n - 1) / 3) of n seated.
    4. chain     the checkpoint's head block (`head_height`, `head_hash`) is the block the public JSON-RPC serves
                 at that height, and it is listed in the public certificate of batch `batch_height`.
    5. root      (only with --verifier and --genesis) runs the published node's verifier program, which decodes
                 the snapshot and rebuilds the state's Merkle root from it plus the checkpoint's `withheld` leaf
                 hashes, and compares it with `state_root`.

WHAT IT PROVES
    Checks 1-4: the downloaded file is the exact file the checkpoint describes; a quorum of the validators that
    are seated now signed the checkpoint's state root for that batch; and the checkpoint points at a real,
    certified block of the public chain. Check 5 adds: the file's contents hash to that root.

WHAT IT DOES NOT PROVE
    - Without check 5 it does NOT show that the file's contents produce `state_root`; that needs decoding every
      state field (a full re-implementation of the node's state encoding). This script does not re-implement it.
      The verifier program used by check 5 is built from the node source; a published build of it is not yet
      available, so today an outside reader can run check 5 only by building it from source.
    - The seated set is read NOW, not at the checkpoint's batch; after a validator-set change an old checkpoint
      may be judged against the wrong set.
    - It trusts the public endpoints for the seated set and the block hash (a reader with their own node should
      point --chain / --rpc at it).
    - Four fields are withheld from the public file and only their hashes are published; their contents are not
      checked.

EXIT CODES
    0  every check that ran passed (prints VERIFIED, and says whether the root check ran)
    1  a check failed
    2  usage error, or an endpoint/file could not be read
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

try:
    from Crypto.Hash import keccak as _k

    def keccak256(b):
        h = _k.new(digest_bits=256)
        h.update(b)
        return h.digest()
except ImportError:
    try:
        from eth_hash.auto import keccak as keccak256
    except ImportError:
        sys.stderr.write("needs pycryptodome or eth-hash for keccak-256\n")
        sys.exit(2)

UA = {"user-agent": "vordium-security-verifier/1", "content-type": "application/json"}

# ---- secp256k1 (pure Python, verification only) ----
P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0] and (a[1] + b[1]) % P == 0:
        return None
    if a == b:
        l = 3 * a[0] * a[0] * pow(2 * a[1], P - 2, P) % P
    else:
        l = (b[1] - a[1]) * pow(b[0] - a[0], P - 2, P) % P
    x = (l * l - a[0] - b[0]) % P
    return (x, (l * (a[0] - x) - a[1]) % P)


def _mul(k, pt):
    r = None
    while k:
        if k & 1:
            r = _add(r, pt)
        pt = _add(pt, pt)
        k >>= 1
    return r


def decompress(pub33):
    if len(pub33) != 33 or pub33[0] not in (2, 3):
        raise ValueError("not a compressed key")
    x = int.from_bytes(pub33[1:], "big")
    y = pow((x * x * x + 7) % P, (P + 1) // 4, P)
    if (y * y - (x * x * x + 7)) % P:
        raise ValueError("not on curve")
    if (y & 1) != (pub33[0] & 1):
        y = P - y
    return (x, y)


def address_of(pt):
    return keccak256(pt[0].to_bytes(32, "big") + pt[1].to_bytes(32, "big"))[12:]


def ecdsa_verify(digest, sig64, pt):
    r, s = int.from_bytes(sig64[:32], "big"), int.from_bytes(sig64[32:], "big")
    if not (0 < r < N and 0 < s <= N // 2):  # low-S only
        return False
    z = int.from_bytes(digest, "big")
    w = pow(s, N - 2, N)
    q = _add(_mul(z * w % N, G), _mul(r * w % N, pt))
    return q is not None and q[0] % N == r


# ---- I/O ----
def get(url, binary=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        data = r.read()
    return data if binary else json.loads(data)


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=30) as r:
        return json.loads(r.read()).get("result")


def parse_report(hexstr):
    b = bytes.fromhex(hexstr)
    if len(b) != 140:
        raise ValueError(f"report is {len(b)} bytes, want 140")
    height = int.from_bytes(b[0:8], "little")
    if int.from_bytes(b[8:16], "little") != 20:
        raise ValueError("bad address length")
    validator = b[16:36]
    root = b[36:68]
    if int.from_bytes(b[68:76], "little") != 64:
        raise ValueError("bad signature length")
    return height, validator, root, b[76:140]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--files", default="https://rpc-testnet.vordium.com/state-sync/testnet")
    ap.add_argument("--chain", default="https://testnet.vordex.xyz/chain")
    ap.add_argument("--rpc", default="https://testnet.vordex.xyz/chain/native")
    ap.add_argument("--checkpoint", default="latest.json", help="checkpoint file name under --files")
    ap.add_argument("--verifier", help="path to the node's snapshot verifier program (enables check 5)")
    ap.add_argument("--genesis", help="genesis manifest file for check 5 (its sha256 must match the checkpoint)")
    ap.add_argument("--keep", help="directory to keep the downloaded files in")
    a = ap.parse_args()
    if bool(a.verifier) != bool(a.genesis):
        print("--verifier and --genesis go together")
        return 2
    files = a.files.rstrip("/")
    try:
        cp_raw = get(f"{files}/{a.checkpoint}", binary=True)
        cp = json.loads(cp_raw)
        state = get(f"{files}/{cp['state_file']}", binary=True)
        reg = get(f"{a.chain.rstrip('/')}/registry/set")["data"]
    except Exception as e:  # noqa: BLE001
        print(f"cannot read an input: {e}")
        return 2
    B, root_hex = cp["batch_height"], cp["state_root"].removeprefix("0x").lower()
    print(f"checkpoint: chain {cp['chain_id']} batch {B} head {cp['head_height']} root {root_hex}")
    ok = True

    # 1. file
    sha = hashlib.sha256(state).hexdigest()
    f_ok = len(state) == cp["state_len"] and sha == cp["state_sha256"].removeprefix("0x").lower()
    print(f"1 file     {'PASS' if f_ok else 'FAIL'}  len {len(state)} (want {cp['state_len']})  sha256 {sha}")
    ok &= f_ok

    # 2. envelope
    e_ok = (state[:8] == b"VORDSNAP" and int.from_bytes(state[8:12], "little") == 3
            and int.from_bytes(state[12:16], "little") == 0)
    print(f"2 envelope {'PASS' if e_ok else 'FAIL'}  magic {state[:8]!r} schema {int.from_bytes(state[8:12], 'little')}")
    ok &= e_ok

    # 3. quorum of attestations
    seated = {}
    for v in reg["seated"]:
        if v.get("hot_pubkey_set") and v.get("hot_pubkey"):
            seated[bytes.fromhex(v["address"].removeprefix("0x"))] = bytes.fromhex(v["hot_pubkey"].removeprefix("0x"))
    n = len(reg["seated"])
    need = n - (n - 1) // 3
    good = set()
    for h in cp["attestations"]:
        try:
            height, val, root, sig = parse_report(h)
        except ValueError as e:
            print(f"  attestation unreadable: {e}")
            continue
        tag = "0x" + val.hex()
        if height != B or root.hex() != root_hex:
            print(f"  {tag}: wrong batch or root")
            continue
        pub = seated.get(val)
        if pub is None:
            print(f"  {tag}: not in the seated set (or no hot key published)")
            continue
        pt = decompress(pub)
        if address_of(pt) != val:
            print(f"  {tag}: published hot key does not derive this address")
            continue
        digest = keccak256(b"\x07" + B.to_bytes(8, "big") + val + root)
        if ecdsa_verify(digest, sig, pt):
            good.add(val)
            print(f"  {tag}: signature valid")
        else:
            print(f"  {tag}: signature INVALID")
    q_ok = len(good) >= need
    print(f"3 quorum   {'PASS' if q_ok else 'FAIL'}  {len(good)} valid of {len(cp['attestations'])} attestations;"
          f" seated {n}, quorum {need}")
    ok &= q_ok

    # 4. chain binding
    try:
        blk = rpc(a.rpc, "eth_getBlockByNumber", [hex(cp["head_height"]), False])
        batch = get(f"{a.chain.rstrip('/')}/batch/{B}")
    except Exception as e:  # noqa: BLE001
        print(f"cannot read the chain: {e}")
        return 2
    head = "0x" + cp["head_hash"].removeprefix("0x").lower()
    c_ok = (blk is not None and blk["hash"].lower() == head and head in [x.lower() for x in batch.get("block_hashes", [])]
            and isinstance(batch.get("qc"), dict))
    print(f"4 chain    {'PASS' if c_ok else 'FAIL'}  public block {cp['head_height']} = "
          f"{blk['hash'] if blk else None}; in certificate of batch {B}: {head in batch.get('block_hashes', [])}")
    ok &= c_ok

    # 5. root (optional)
    ran5 = False
    if a.verifier:
        d = a.keep or tempfile.mkdtemp(prefix="vsnap-")
        os.makedirs(d, exist_ok=True)
        cpp, stp = os.path.join(d, "checkpoint.json"), os.path.join(d, cp["state_file"])
        open(cpp, "wb").write(cp_raw)
        open(stp, "wb").write(state)
        r = subprocess.run([a.verifier, cpp, stp, a.genesis], capture_output=True, text=True)
        print("5 root     verifier output:")
        for line in (r.stdout + r.stderr).strip().splitlines():
            print("    " + line)
        print(f"5 root     {'PASS' if r.returncode == 0 else 'FAIL'}  (verifier exit {r.returncode})")
        ok &= r.returncode == 0
        ran5 = True
    else:
        print("5 root     NOT RUN  (needs --verifier and --genesis; see the header)")
    if a.keep and not a.verifier:
        os.makedirs(a.keep, exist_ok=True)
        open(os.path.join(a.keep, "checkpoint.json"), "wb").write(cp_raw)
        open(os.path.join(a.keep, cp["state_file"]), "wb").write(state)

    if ok:
        print("VERIFIED" + ("" if ran5 else " (checks 1-4; root recompute not run)"))
        return 0
    print("FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
