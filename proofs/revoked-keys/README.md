# A revoked agent or session key cannot trade

**BUILT, NOT PROVEN**

## Network

Testnet; local test for the AI server

## Code version

The testnet network on the run date

## Check it yourself

On the testnet, end an agent in Vordex → Agents, then ask it to place an order. The network refuses it and no order rests on the book.

## Last run (UTC date)

9 Nov 2026

## Result

An order signed by a revoked or replaced session key was refused; an order or agent action that reused an order number was refused; after an agent was revoked, no order of it was held.

## Limits

An order signed just before a revoke and applied just after it is not yet tested. Expired sessions, expired agents and expired agent policies are not yet tested on a network. Not yet checked on mainnet.

Also on the docs: https://docs.vordium.com/security/ai-audit/#revoked-keys
