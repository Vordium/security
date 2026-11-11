# The network stop ends every signer at once

**PROVED**

## Network

Testnet

## Code version

Testnet node release 043e1fc813ec08b2

## Check it yourself

Run by the team

## Last run (UTC date)

11 Nov 2026

## Result

One stop signed by the account's wallet ended its trading key and its agent at once: within about one second the network showed no session and no live agent, and the next order of the agent and of the old trading key were both refused. Sending the same signed stop again was refused. 15 of 15 checks passed.

## Limits

The network's records show the stop's effect: no session, no live agent, and no order after the stop. The refusals of the next orders happen before an order is recorded, so they rest on the run's own log, not on the network's records. This stop does not cancel resting orders: they stay on the book until cancelled. Not yet available on mainnet, where the app ends each agent and the trading key one by one instead.

Also on the docs: https://docs.vordium.com/security/ai-audit/#stop-signers
