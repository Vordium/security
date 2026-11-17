# SHIELD A — accounting replay (test network)

**Scope.** Every customer balance change the chain recorded, checked against the records that explain it, from public reads.
**Kit.** `kit/replay_balances.py` (sha256 in SHA256SUMS). **Run:** 2026-11-17.

**Vectors: 14** — covered 9 · by design 3 · open 2.

| Check | Result |
|---|---|
| Parts add up to the collateral; delta = after − before; explained exactly when unexplained is 0 | PASS |
| The named records' legs add up to the change (fills: taker and maker; funding; vault moves; …) | PASS |
| The last leg's balance equals the new balance | PASS |
| Each change follows the account's previous change exactly (no skipped or dropped change) | PASS |
| No customer account has an unexplained change | PASS |
| No fill pairs an account with itself | PASS |

Window: every balance record since the chain started writing them, heights 292,555,217 – 292,844,118: 20,406 records,
4,031 balance changes, **4,031 judged, 0 problems, 0 excluded**. Record kinds seen in this window: fills, funding, order
and stop records, vault create/deposit/withdraw/close. The other money kinds (deposits, withdrawals, refunds, liquidations,
ADL, staking, pool, claims, treasury, spot) are covered by the same rule and by the published fixtures; they did not occur
in this window.

**Rule tests:** 25 cases; 17 of 17 planted faults caught (each rule removed in turn).

**By design (stated by the chain):** system accounts (fee treasury, pool, vaults, house) are counted, not judged; a leg the
chain marks as not measured is excluded and counted; a listed gap or restart starts a new baseline.

**Open:** a per-tick funding conservation rule (Σ payments = 0 plus any named term) is not yet stated; the system-funds term
is not published.

**Re-run:** `python3 kit/replay_balances.py --chain https://testnet.vordex.xyz/chain-archive --from-height 292555217`
