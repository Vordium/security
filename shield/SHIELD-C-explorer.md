# SHIELD C — explorer truth (VordScan, both networks)

**Scope.** Every number the explorer serves that has a chain source: its truth file, live facts, block hashes, market
rules, and how far its block index is behind the chain. **Kit.** `kit/crosscheck_explorer.py`. **Run:** 2026-11-17.

**Vectors: 7** — covered 5 · partly 1 · open 1.

| Check | Main network | Test network |
|---|---|---|
| X1 truth file facts = their named sources | PASS | PASS |
| X2 chain id, genesis, trading/deposit state, validator count | PASS | PASS |
| X2 protocol upgrades on/off by name | **3 of 32 differ** (open item 1) | PASS |
| X3 block hashes = the certificates | PASS | not read (explorer API errors) |
| X4 market rules = the chain's specs | PASS | PASS |
| X5 block index at most 120 s behind the chain | **FAIL: about 7 h behind** (open item 2) | not read |

Totals — main network: 74 values agree, 4 differ; test network: 121 agree, 0 differ, 12 not read (INCOMPLETE).

**Open items:**
1. Three protocol upgrades that are on are shown as off on the main network explorer (its facts feed kept an older
   configuration after an update). Fix ready; it ships with the operator's approval, then X2 is re-run.
2. The main network explorer's block index is about 7 hours behind the chain (its indexer is slower than the chain since
   the chain's height rate went up). A freshness alarm now watches it; the cause is fixed by giving the explorer its own
   server, planned for the new genesis. The test network explorer is also behind and its API is failing reads.

**Re-run:** `python3 kit/crosscheck_explorer.py --site https://vordscan.io --chain https://rpc.vordium.com`
