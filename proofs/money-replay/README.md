# Balances follow the public records on the testnet

**PROVED**

## Network

Testnet

## Code version

The testnet network on the run date

## Check it yourself

`python3 verifiers/money_replay.py --minutes 30 ACCOUNT [ACCOUNT ...]`; self-test `python3 verifiers/money_replay.py --self-test verifiers/money-replay-cases.json`

## Last run (UTC date)

15 Nov 2026 16:42–17:28 UTC (heights 272,120,839 to 272,572,743)

## Verifier

`python3 verifiers/money_replay.py`

## Result

A public script followed 6 accounts for 45 minutes and read each balance 150 times, 900 reads in all (7 could not be placed at one height or tied to the previous read, and were skipped). Between two balance reads placed at one height, it checked that the change of free balance plus order margin plus position margin equals the sum of the account's public records in between (taker fills: realised PnL minus fee plus rebate; funding payments; book liquidations: their fee). It counts a step only when the account had a record or a balance change in it: 120 such steps, from 3 of the 6 accounts (the other 3 had none in the window). 104 matched to the micro-USDC, 16 could not be replayed (maker fills), 0 differed. Across the 120 steps the records held 152 fills and 85 funding payments. The run's own record is runs/money-replay/results.json, signed with the release key (runs/money-replay/results.json.asc).

## Limits

Maker fills record no fee and no realised PnL yet, so a step with a maker fill is not replayed. Balances cannot be read at a past height yet, so the check runs forward from the moment it starts; a past partial liquidation or oracle pause cannot be replayed. Records it does not read (deposits, withdrawals, transfers, app fees, other liquidation kinds) make a step not replayable, never a match. It trusts the endpoints it reads unless pointed at your own node.
