#!/usr/bin/env python3
"""Vordium: check that recent public blocks link to each other and match their batches' finality certificates.

Author: Vordium. License: Apache-2.0.

USAGE
    python3 verify_block_links.py [--network mainnet|testnet] [--batches 20] [--rpc URL --read URL]

    mainnet  JSON-RPC https://rpc.vordium.com            reads https://rpc.vordium.com
    testnet  JSON-RPC https://testnet.vordex.xyz/chain/native   reads https://testnet.vordex.xyz/chain
    Reads only:  GET /batches?from_height=<max>  (newest certified batch), GET /batch/{n} (heights, block_hashes, qc),
                 JSON-RPC eth_getBlockByNumber for every height a batch lists.

REQUIREMENTS
    Python 3.8+, standard library only.

HOW BLOCKS ARE LAID OUT
    Blocks are produced in batches; each batch fills a few consecutive heights and leaves the rest of its height range
    empty. Every block of batch n is built on the same parent: the last block of batch n-1. One certificate (`qc`)
    finalizes the whole batch and names its last block.

WHAT IT CHECKS, for the newest `--batches` consecutive certified batches
    a. the certificate's list of block hashes equals, in order, the hashes the JSON-RPC serves at the listed heights;
    b. the listed heights are consecutive and every other height in between batches is empty (served as null);
    c. every block's parentHash equals the last block hash of the previous batch;
    d. the certificate names the batch's last block (`qc.block_hash`, `qc.height`) and carries a signer count.
    That covers N = sum of the batches' block counts consecutive non-empty blocks.

WHAT IT PROVES
    Two independent public reads (the block read and the certificate read) agree on an unbroken chain of blocks, each
    building on the block the previous certificate finalized: no fork, gap or swapped block in the window read.

WHAT IT DOES NOT PROVE
    - It does not recompute a block hash from the block's contents (that needs the node's block encoding), and it
      does not verify the certificate's signatures (the public read lists the signers, not the signatures).
    - It trusts that the endpoint you query is honest; point --rpc / --read at your own node to remove that trust.
    - It looks only at the window read, not the whole history.

EXIT CODES
    0  every check passed
    1  a check failed (each failure is printed)
    2  usage error or an endpoint could not be read
"""
import argparse
import json
import sys
import urllib.request

NETS = {"mainnet": ("https://rpc.vordium.com", "https://rpc.vordium.com"),
        "testnet": ("https://testnet.vordex.xyz/chain/native", "https://testnet.vordex.xyz/chain")}
UA = {"user-agent": "vordium-security-verifier/1", "content-type": "application/json"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return json.loads(r.read())


def block(rpc, h):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber", "params": [hex(h), False]}).encode()
    with urllib.request.urlopen(urllib.request.Request(rpc, data=body, headers=UA), timeout=15) as r:
        return json.loads(r.read()).get("result")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--network", choices=NETS, default="mainnet")
    ap.add_argument("--batches", type=int, default=20)
    ap.add_argument("--rpc")
    ap.add_argument("--read")
    a = ap.parse_args()
    rpc, read = a.rpc or NETS[a.network][0], (a.read or NETS[a.network][1]).rstrip("/")
    if a.batches < 2:
        print("--batches must be at least 2")
        return 2
    try:
        top = get(f"{read}/batches?from_height=18446744073709551615")["history"]["to_batch"]
        batches = [get(f"{read}/batch/{n}") for n in range(top - a.batches + 1, top + 1)]
    except Exception as e:  # noqa: BLE001
        print(f"cannot read batches: {e}")
        return 2
    fails, nblocks, prev_last, prev_top = [], 0, None, None
    for b in batches:
        n, hs, want = b["batch_height"], b.get("heights", []), [x.lower() for x in b.get("block_hashes", [])]
        qc = b.get("qc") or {}
        if not hs or len(hs) != len(want):
            fails.append(f"batch {n}: heights/hashes missing or unequal ({len(hs)} vs {len(want)})")
            continue
        if hs != list(range(hs[0], hs[0] + len(hs))):
            fails.append(f"batch {n}: heights not consecutive {hs}")
        try:
            if prev_top is not None:
                for h in range(prev_top + 1, hs[0]):
                    if block(rpc, h) is not None:
                        fails.append(f"height {h} between batches is not empty")
            got = [block(rpc, h) for h in hs]
        except Exception as e:  # noqa: BLE001
            print(f"cannot read blocks: {e}")
            return 2
        for h, w, g in zip(hs, want, got):
            nblocks += 1
            if g is None:
                fails.append(f"height {h}: no block served, certificate lists {w}")
                continue
            if g["hash"].lower() != w:
                fails.append(f"height {h}: served {g['hash']} but certificate lists {w}")
            if prev_last is not None and g["parentHash"].lower() != prev_last:
                fails.append(f"height {h}: parent {g['parentHash']} is not the previous batch's last block {prev_last}")
        if (qc.get("block_hash") or "").lower() != want[-1] or qc.get("height") != hs[-1] or not qc.get("signer_count"):
            fails.append(f"batch {n}: certificate does not name its last block {hs[-1]} {want[-1]}")
        print(f"batch {n}: heights {hs[0]}..{hs[-1]} ({len(hs)} blocks) last {want[-1][:18]}..."
              f" signers {qc.get('signer_count')}")
        prev_last, prev_top = want[-1], hs[-1]
    for f in fails:
        print("FAIL " + f)
    print(f"{'PASS' if not fails else 'FAIL'}: {len(batches)} batches, {nblocks} blocks, {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
