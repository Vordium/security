# SHIELD D — one finalized history and finality (both networks)

**Scope.** Finalized batches over a window: certificates, signers, heights, block links, a second host, records and op-order
digests, block times; and time to finality. **Kit.** `kit/verify_history.py`. **Run:** 2026-11-17.

**Vectors: 12** — covered 9 · measured 1 · open 2 (+ 2 parts open inside covered rows).

| Check | Test network (30 batches) | Main network (20 batches) |
|---|---|---|
| H1–H4 certificate held and complete; signers seated with a quorum of power; heights and certified block consistent; no height in two batches | PASS (30) | PASS (20) |
| H5 every block links to the previous batch's last block | PASS (195 links) | PASS (133 links) |
| H6 a second host serves the same history | PASS (30) | — |
| H7 records digest recomputed | PASS (8) | — (no records in the window) |
| H8 op-order digest recomputed | PASS (202 blocks) | PASS (140 blocks) |
| H9 block times never go back; none ahead of our clock | PASS | PASS |
| Finality (certificate visible − last block time), upper bound | p50 1.52 s · p95 6.81 s · p99 7.10 s | p50 2.76 s · p95 3.48 s · p99 3.50 s |

Planted faults (a certified hash, an outside signer, a records digest, a parent link) are each caught.
**Rule tests:** 17 cases; 11 of 11 planted faults caught.

**Open:** certificates carry no public signatures (who signed is taken from the host; two hosts are compared); each op's
own hash is not recomputable outside the node; the main network has no public state export to rebuild the state root.

**Re-run:** `python3 kit/verify_history.py --chain https://testnet.vordex.xyz/chain --second-chain https://testnet.vordex.xyz/chain-archive --batches 40 --finality-seconds 60`
