# A revoked agent or session key cannot trade

**BUILT, NOT PROVEN**

## Network

Testnet; local test for the AI server

## Code version

The testnet network on the run date

## Check it yourself

On the testnet, run the agent-control proof script with a funded test account; its revoke step records each order's outcome, the heights between which the revoke applied, and the agent's orders still on the book after it.

## Last run (UTC date)

13 Nov 2026 (orders in flight during a revoke, on the testnet)

## Verifier

`python3 verifiers/agent_control_proof.py`

## Result

An agent's orders were sent one after another while its owner revoked it. The orders that arrived before the revoke applied were accepted; every order after it was refused when received (code no_session), and an order signed by the revoked agent a minute later was refused the same way. Reading the agent back to back showed the revoke applied less than one second after it was sent. An order signed by a revoked or replaced session key was refused, and an order that reused an order number was refused.

## Limits

Revoking an agent does not cancel the orders it already has on the book: in two runs they stayed on the book for 30 and 60 seconds, until the owner cancelled them. Cancel an agent's open orders when you revoke it. The network gives no public record of the height at which a revoke applied; the proof bounds it by reading the agent before and after. Expired sessions, expired agents and expired agent policies are not yet tested on a network. Not yet checked on mainnet.

Also on the docs: https://docs.vordium.com/security/ai-audit/#revoked-keys
