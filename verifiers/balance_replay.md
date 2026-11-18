# Balance records replay (Vordium testnet)

Checks, step by step, that each account's collateral follows the network's public money records. It reads only the
records, so it can check past heights, not only the minutes after it starts.

It uses the Python 3 standard library only (no packages, no keys) and reads public data:

- `<records>/events/coverage`: the records' revision (`records_schema_revision`, 4) and the money record kinds
- `<records>/events/account/<account>`: the account's `balance_change` records and the money records that name it

Default records: `https://testnet.vordex.xyz/chain-archive` (`--records URL` to point it at your own node).

## Run it

    python3 verifiers/balance_replay.py ACCOUNT [ACCOUNT ...]
    python3 verifiers/balance_replay.py --from-height H1 --to-height H2 ACCOUNT
    python3 verifiers/balance_replay.py --self-test verifiers/balance-replay-cases.json

By default it checks the latest 20,000 heights (`--blocks N`). It writes a trace (`--out`, default
`balance-replay-trace.json`) with every step, its legs and its verdict.

Exit codes: 0 every checked step matched (at least one) · 1 a step differs, or an account that is not a protocol account
has an unexplained step · 2 could not run · 3 nothing was checked. Self-test: 0 every case gives its listed verdicts · 1 a
case does not.

## How a step is checked

- The network writes one `balance_change` record per account per change. It carries the collateral before and after, in
  four parts (`usdc_6dec`, `reserved_orders_6dec`, `in_positions_6dec`, `spot_reserved_6dec`, with their sum in
  `collateral_6dec`), and the cursors of the money records that made the change (`records`). `since_cursor` links it to
  the account's previous one.
- Every money record says what it moved each account by: `account_delta_6dec` in its `legs`, in its `taker` and `maker`
  parts (a fill), or on the record itself (a liquidation).
- A step **matches** when collateral before + the sum of this account's changes in the records it names = collateral
  after, `collateral_6dec` is the sum of its parts, and the record's own `delta_6dec` and `records_delta_6dec` agree.
- When the account's previous step was read, the step must also start where that one ended, and its `since_cursor` must
  name it; otherwise the step is **different** (the chain is broken). A step with no `since_cursor` after a step that was
  read starts a new chain: the move between the two is **not checked**, never a match. The first step in the window is
  judged on its own.
- A step the network itself marks unexplained (`explained` false, or `unexplained_6dec` not 0) is shown as
  **unexplained**, never as a match.
- A gap record (`gap`, with `gap_reason` dropped or restore), a leg that could not be measured (`notes_missing`), a leg
  with no amount, a record the step names that was not read, a record named twice, or two different records on one cursor
  it names is shown as **not checked** (or **different** when a value is not a number), with the reason, never as a
  match. No step is judged across a gap.
- The money record kinds come from the records' own list (`money_record_kinds`), never from a list in the script.
- A step may also name an order record (`order_closed`, `order_updated`). An order closing or changing size moves margin
  between `reserved_orders` and `usdc`, so collateral does not change: such a record counts as zero, but only when it is
  the only record on its cursor, names the account, and carries no legs, no taker or maker block and no micro-USDC amount.
  Any other named record outside the money list is **not checked**.
