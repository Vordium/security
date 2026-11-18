# Each balance record adds up from the money records it names, on the testnet

**PROVED**

## Network

Testnet

## Code version

The testnet network on the run date

## Check it yourself

`python3 verifiers/balance_replay.py --from-height H1 --to-height H2 ACCOUNT [ACCOUNT ...]`; self-test `python3 verifiers/balance_replay.py --self-test verifiers/balance-replay-cases.json`

## Last run (UTC date)

18 Nov 2026 (heights 300,000,000 to 300,176,327)

## Verifier

`python3 verifiers/balance_replay.py`

## Result

The network writes one balance record per account per change, with the collateral before and after in four parts (free USDC, order margin, position margin, spot reserve) and the money records that made the change. A public script read every balance record of 8 accounts over 176,327 heights: 41 steps, from the 3 accounts that had a change (the other 5 had none). All 41 added up to the micro-USDC (collateral before plus the account's legs in the records named equals collateral after), 38 started exactly where the account's previous step ended (the other 3 are each account's first step in the window), 0 differed, 0 were marked unexplained by the network and 0 were left not checked. 32 order records named by a step (an order closing or changing size, which moves margin inside collateral) counted as zero. The run's own record is runs/balance-replay/results.json, signed with the release key (runs/balance-replay/results.json.asc).

## Limits

8 accounts over one window of heights. An order record counts as zero only when it carries no legs and no micro-USDC amount. Gap records, resets and legs that could not be measured are shown as not checked, never as a match. It trusts the endpoints it reads unless pointed at your own node.
