# Vordium re-run kit

Four scripts that let anyone check Vordium from the outside. They use public reads only: no account, no key, no sign-up.
They need Python 3.9 or later and nothing else (the Keccak-256 hash is included).

Every script prints what it checked, what it could not check and why, and one result line:

| Result | Meaning |
|---|---|
| `PASS` | every check that ran agreed, and nothing it was asked to check went unread |
| `FAIL` | at least one value is wrong; the line names it |
| `INCOMPLETE` | nothing was wrong, but something could not be read — never counted as a pass |
| `NOT RUN` / `NOTHING JUDGED` | the script could not do its job (the reason is printed) |

Exit codes follow the same order: 0 pass, 1 fail, 2 incomplete or not run, 3 nothing checked.

Public hosts used below:
- test network node: `https://testnet.vordex.xyz/chain` (archive host with the full record history: `https://testnet.vordex.xyz/chain-archive`)
- main network node: `https://rpc.vordium.com`
- explorer: `https://testnet.vordscan.io`, `https://vordscan.io`
- Arbitrum (for the vaults): any Arbitrum One / Arbitrum Sepolia RPC you trust, e.g. `https://arb1.arbitrum.io/rpc`, `https://sepolia-rollup.arbitrum.io/rpc`

## 1. Replay balances — `replay_balances.py`

The chain writes a `balance_change` record every time an account's money moves, naming the records that explain it
(fills, funding, fees, deposits, withdrawals, refunds, vault moves, liquidations, ADL, …). The script re-adds every leg and
checks that nothing moved without a record.

```
python3 replay_balances.py --chain https://testnet.vordex.xyz/chain-archive --minutes 30
python3 replay_balances.py --chain https://testnet.vordex.xyz/chain-archive --from-height <h> --account 0x…
```

For every change: the parts add up to the collateral; delta = after − before; the named records' legs add up to the change;
the last leg's balance equals the new balance; the change follows the account's previous change exactly; and a customer
account never has an unexplained change. Changes it does not judge are counted with the reason (system accounts such as the
fee treasury, a leg the chain marks as not measured, a gap the chain lists).

## 2. Verify reserves — `verify_reserves.py`

```
python3 verify_reserves.py --chain https://testnet.vordex.xyz/chain \
    --arbitrum-rpc https://sepolia-rollup.arbitrum.io/rpc --address 0xYOUR_ADDRESS --second-chain https://testnet.vordex.xyz/chain-archive
```

- R1: the coverage answer follows its own rule (covered exactly when the USDC held covers what is owed; the ratio is floored).
- R2: you read each vault's USDC on Arbitrum yourself, at the block the answer names; the sum must equal the answer to the unit.
- R3: a second host publishes the same liabilities root for the same height.
- R4: your own balance is a leaf of that tree: the proof walks to the root by the published rule.

Limit stated by the chain: the tree proves that your balance is included; it does not prove the total (a sum tree is planned).

## 3. Verify one finalized history — `verify_history.py`

```
python3 verify_history.py --chain https://testnet.vordex.xyz/chain --second-chain https://testnet.vordex.xyz/chain-archive \
    --batches 40 --finality-seconds 60
```

Per finalized batch: the certificate is held and complete; its signers are seated validators holding a quorum of voting
power; heights, hashes and the certified block agree; every block links to the previous batch's last block; a second host
serves the same history; the records digest and each block's op-order digest are recomputed. With `--finality-seconds`
it measures, for new batches, the time from the last block to a visible certificate (p50 / p95 / p99). This includes the
host's own read delay, so it is an upper bound.

Limit: certificates list their signers but carry no signatures on the public reads, so who signed is taken from the host;
comparing two hosts reduces that trust.

## 4. Cross-check the explorer — `crosscheck_explorer.py`

```
python3 crosscheck_explorer.py --site https://vordscan.io --chain https://rpc.vordium.com
```

The explorer's `/truth.json` facts against the sources they name; its live facts (chain id, trading and deposit state,
protocol upgrades on/off) against the chain's own answers; block hashes against the certificates; market rules against the
chain's specs; and how far the explorer's block index is behind the chain (`--max-lag`, default 120 s).

## Tests

`python3 tests/test_replay.py`, `tests/test_reserves.py`, `tests/test_history.py` change one rule at a time in a copy of the
script and confirm that a planted fault is caught; `--self-test` on each script runs its rule cases.
