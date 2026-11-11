# Two agents cannot overspend one account

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

Two orders of one account, each needing more than half of its free balance, were sent within one millisecond: by two agents, and by the owner and an agent. In all 4 runs the network accepted exactly one and refused the other for insufficient margin in the same block, and never reserved more than the account held.

## Limits

It proves that two orders sent at once were judged one after the other within one block against one shared balance; it does not cover more than two signers at once. Not yet run on mainnet.

Also on the docs: https://docs.vordium.com/security/ai-audit/#shared-collateral
