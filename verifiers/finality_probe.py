#!/usr/bin/env python3
"""Vordium: measure, from outside, how long after a batch's last block its finality certificate becomes readable.

Author: Vordium. License: Apache-2.0.

USAGE
    python3 finality_probe.py [--network mainnet|testnet | --base URL] [--seconds 60] [--poll-ms 100]
                              [--max-p50-ms N] [--max-p99-ms N] [--quiet]

    mainnet  https://rpc.vordium.com
    testnet  https://testnet.vordex.xyz/chain
    Reads only:  GET /batches?from_height=<max>   (newest certified batch number, `history.to_batch`)
                 GET /batch/{n}                   (`qc` certificate object, `last_block_time_ms`)

REQUIREMENTS
    Python 3.8+, standard library only. Run it on a machine whose clock is synchronised (NTP); record its offset.

METHOD
    It starts at the batch after the newest certified one, so every batch it measures was NOT yet certified when
    watching began. Every `--poll-ms` it asks for the next batch; when the answer carries a certificate (`qc`) it records
        finality(n) = (local wall clock at that first answer) - last_block_time_ms of batch n
    and moves straight to the next batch, so it keeps up with the chain.

WHAT IT PROVES
    That batches keep being finalized (a certificate signed by a quorum of validators exists) while you watch, and the
    latency a public reader actually sees: certificate formation + storage + public read path + network + up to one
    poll interval. It is an UPPER bound on consensus finality as experienced through the public endpoint.

WHAT IT DOES NOT PROVE
    - It does not check the certificate's signatures (the public read lists the signers, not the signatures).
    - Two clocks are compared (the block producer's and yours): any offset between them is added to every sample,
      and a large skew can produce negative samples, which are counted, not hidden.
    - It is not a measurement of consensus alone, and a short window says nothing about behaviour under faults.
    - Behind a load balancer two read services may answer alternately; numbers from different paths are not mixed.

EXIT CODES
    0  samples collected (and within --max-p50-ms / --max-p99-ms when given)
    1  no batch was certified during the window, or a given limit was exceeded
    2  usage error or the endpoint could not be read
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

NETS = {"mainnet": "https://rpc.vordium.com", "testnet": "https://testnet.vordex.xyz/chain"}
UA = {"user-agent": "vordium-security-verifier/1"}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--network", choices=NETS, default="mainnet")
    ap.add_argument("--base", help="read endpoint (overrides --network)")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--poll-ms", type=int, default=100)
    ap.add_argument("--max-p50-ms", type=float)
    ap.add_argument("--max-p99-ms", type=float)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    base = (a.base or NETS[a.network]).rstrip("/")
    try:
        st, h = get(f"{base}/batches?from_height=18446744073709551615")
        start = h["history"]["to_batch"] + 1
    except Exception as e:  # noqa: BLE001
        print(f"cannot read {base}/batches: {e}")
        return 2
    n, samples, negative, no_time = start, [], 0, 0
    deadline = time.monotonic() + a.seconds
    while time.monotonic() < deadline:
        tick = time.monotonic()
        while True:
            try:
                st, b = get(f"{base}/batch/{n}")
            except Exception:  # noqa: BLE001
                break
            if st != 200 or not b or not isinstance(b.get("qc"), dict):
                break
            now_ms = time.time() * 1000
            t = b.get("last_block_time_ms")
            if t is None:
                no_time += 1
            else:
                f = now_ms - t
                negative += f < 0
                samples.append(f)
                if not a.quiet:
                    print(f"batch {n}: finality {f:.0f} ms ({b.get('block_count')} blocks,"
                          f" {b['qc'].get('signer_count')} signers)")
            n += 1
        time.sleep(max(0.0, a.poll_ms / 1000 - (time.monotonic() - tick)))
    if not samples:
        print(f"FAIL: no batch certified in {a.seconds:.0f} s (watched from batch {start})")
        return 1
    r = {"method": "passive_batch_poll", "base": base, "poll_ms": a.poll_ms, "samples": len(samples),
         "from_batch": start, "to_batch": n - 1, "p50_ms": round(pct(samples, 50)), "p90_ms": round(pct(samples, 90)),
         "p99_ms": round(pct(samples, 99)), "max_ms": round(max(samples)), "negative_samples": negative,
         "skipped_no_block_time": no_time, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print(json.dumps(r))
    bad = (a.max_p50_ms is not None and r["p50_ms"] > a.max_p50_ms) or \
          (a.max_p99_ms is not None and r["p99_ms"] > a.max_p99_ms)
    print("FAIL: over the given limit" if bad else "PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
