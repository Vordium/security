# Balances follow the public records on the testnet

**PROVED**

## Network

Testnet

## Code version

The testnet network on the run date

## Check it yourself

`python3 verifiers/money_replay.py --minutes 45 ACCOUNT [ACCOUNT ...]`; self-test `python3 verifiers/money_replay.py --self-test verifiers/money-replay-cases.json`

## Last run (UTC date)

16 Nov 2026 14:37–15:22 UTC (heights 285,325,095 to 285,723,367)

## Verifier

`python3 verifiers/money_replay.py`

## Result

A public script followed 6 accounts for 45 minutes and read each balance 84 times, 504 reads in all (9 could not be placed at one height or tied to the previous read, and were skipped). Between two balance reads placed at one height, it checked that the change of free balance plus order margin plus position margin equals the sum of the account's public records in between (taker fills: realised PnL minus fee plus rebate; funding payments; book liquidations: their fee). It counts a step only when the account had a record or a balance change in it: 97 such steps, from 3 of the 6 accounts (the other 3 had none in the window). 81 matched to the micro-USDC, 16 could not be replayed (maker fills), 0 differed. Across the 97 steps the records held 121 fills and 109 funding payments. The run's own record is runs/money-replay/results.json, signed with the release key (runs/money-replay/results.json.asc).

## Limits

Maker fills record no fee and no realised PnL yet, so a step with a maker fill is not replayed. Balances cannot be read at a past height yet, so the check runs forward from the moment it starts; a past partial liquidation or oracle pause cannot be replayed. Any record it does not read that names the account, in any field (deposits, withdrawals, transfers, app fees, other liquidation kinds), makes a step not replayable, never a match. It trusts the endpoints it reads unless pointed at your own node.
