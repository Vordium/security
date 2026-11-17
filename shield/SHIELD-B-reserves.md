# SHIELD B — reserves (test network and main network)

**Scope.** The chain's coverage answer, the vaults' USDC on Arbitrum, the liabilities tree and per-account proofs.
**Kit.** `kit/verify_reserves.py`. **Run:** 2026-11-17.

**Vectors: 8** — covered 4 · partly 1 · by design 1 · open 2.

| Check | Test network | Main network |
|---|---|---|
| R1 coverage follows its rule (covered ⇔ held ≥ owed; ratio floored) | PASS (ratio 5.517180) | PASS (nothing owed) |
| R2 vaults' USDC read on Arbitrum = the answer, to the unit | PASS (1,964,500.560926 USDC) | PASS (0) |
| R3 a second host publishes the same root at the same height | PASS | — |
| R4 an account's proof walks to the published root | PASS (a sample account: included) | PASS (no leaves; balance 0) |

A planted +1 micro-USDC in the answer is caught (R2 FAIL). **Rule tests:** 14 cases; 9 of 9 planted faults caught.

**By design:** the tree proves inclusion, not the total (a sum tree is planned); "not in the tree" is the chain's claim,
backed by the account's balance now (no public read gives a past balance).
**Open:** the liabilities root is not yet carried in certified state; the insurance balance has no independent read.

**Re-run:** `python3 kit/verify_reserves.py --chain https://testnet.vordex.xyz/chain --arbitrum-rpc <your Arbitrum Sepolia RPC> --address <your address>`
