# Agent limits are enforced by the network

**BUILT, NOT PROVEN**

## Network

Testnet

## Code version

The testnet network and Vordex testnet app on the run date

## Check it yourself

On the testnet, run the agent-control proof script with a funded test account, or create an agent in Vordex → Agents with a small largest order and one market, then ask it for a larger order or another market. The network refuses it.

## Last run (UTC date)

13 Nov 2026 (public agent-control proof on the testnet, daily loss included); 5 Nov 2026 (1,000 orders compared with the pre-trade check)

## Verifier

`python3 verifiers/agent_control_proof.py`

## Result

A public proof script, rerunnable by anyone with the public SDK, registered an agent allowed to trade one market with a largest order of 0.02, a total exposure cap, a leverage cap, a daily loss limit of 0.01 USDC and an expiry. An allowed order was accepted and rested on the book. An order in another market was refused when received with agent_refused / market_not_allowed, and an order twice the largest size with agent_refused / max_order. The agent then bought and sold across the spread: after two round trips its realised loss for the day was 0.076 USDC, past its limit. In the same step the network locked the agent to reduce-only (lock_daily_loss_limit) and cancelled its resting order that would have added to its position. Its next opening order was refused when received with agent_refused / reduce_only_or_side. In the 1,000-order comparison, the pre-trade check and the network agreed on every order except at the very edge of the price band, and the network refused orders above the total exposure limit.

## Limits

An order refused because of the daily loss lock carries the code reduce_only_or_side, not daily_loss_limit; the lock itself is shown in the agent's record and events. Exposure limits with an existing position, and the largest position, are not yet tested. Not yet checked on mainnet.

Also on the docs: https://docs.vordium.com/security/ai-audit/#agent-limits
