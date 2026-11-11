# Agent limits are enforced by the network

**BUILT, NOT PROVEN**

## Network

Testnet

## Code version

The testnet network and Vordex testnet app on the run date

## Check it yourself

On the testnet, create an agent in Vordex → Agents with a small largest order and one market, then ask it for a larger order or another market. The network refuses it.

## Last run (UTC date)

7 Nov 2026 (refusals); 5 Nov 2026 (1,000 orders compared with the pre-trade check)

## Result

The network refused orders above the largest order size, above the leverage limit and in markets the agent is not allowed to trade. In the 1,000-order comparison, the pre-trade check and the network agreed on every order except at the very edge of the price band, and the network refused orders above the total exposure limit.

## Limits

The daily loss limit has not yet been shown to stop an agent on a network. Exposure limits with an existing position, and the largest position, are not yet tested. Not yet checked on mainnet. The recurring testnet check does not currently complete its setup step, so its last full pass is the date above.

Also on the docs: https://docs.vordium.com/security/ai-audit/#agent-limits
