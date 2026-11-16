# Money replay (Vordium testnet)

Follows one or more accounts' collateral through their public chain records and checks, at every step, that the
balance the records predict equals the balance the chain reports.

It uses the Python 3 standard library only (no packages, no keys) and reads public data:

- `<chain>/status`
- `<chain>/balance/<account>`
- `<records>/events/account/<account>`

Defaults: chain `https://testnet.vordex.xyz/chain`, records `https://testnet.vordex.xyz/chain-archive`
(`--chain URL`, `--records URL` to point it at your own node).

## Run it

    python3 verifiers/money_replay.py --minutes 30 ACCOUNT [ACCOUNT ...]
    python3 verifiers/money_replay.py --self-test verifiers/money-replay-cases.json

`--step` sets the seconds between two balance reads of one account (default 15). It writes a trace (`--out`, default
`money-replay-trace.json`) with every counted step, its records and its verdict. A step is counted only when the account
had a record or a balance change in it; a read that cannot be placed at one height or tied to the previous read is skipped and counted as unanchored.

Exit codes: 0 every replayable step matched (at least one) · 1 a step differs · 2 could not run · 3 nothing was checked.
Self-test: 0 every case gives its listed verdict · 1 a case does not.

## How a step is checked

- A balance read is taken between two head reads (h1, h2). It counts as the balance at h1 when the head did not go
  back, the records route has stored every height up to h2 with no gap in the window, and the account has no record
  inside [h1, h2].
- Between two such reads, the change of `total + reserved_orders + in_positions` must equal the sum of the account's
  records in between:
  - fill, this account's taker leg: `realized_pnl_6dec - fee_paid_6dec + rebate_6dec`
  - `funding_payment`: `payment_6dec`
  - liquidation of kind `book`: `- fee_6dec`
- A taker fee above the listed rate makes the step **different**.
- A step with a maker leg, another liquidation kind, an app fee or any other record that may move money is **not
  replayable**, never a match.

## The signed run

`runs/money-replay/results.json` is the record of one run (6 accounts, 45 minutes, 900 reads, 120 counted steps:
104 match, 16 not replayable, 0 different). It lists the sha256 of `money_replay.py` and of the shared cases
(`money-replay-cases.json`; named `cases.json` in the record). `runs/money-replay/results.json.asc` is its signature
with the release key.
