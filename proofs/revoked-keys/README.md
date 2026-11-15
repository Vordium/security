# A revoked agent or session key cannot trade

**BUILT, NOT PROVEN**

## Network

Testnet; local test for the AI server

## Code version

Testnet node release 5124130b5d8564ba

## Check it yourself

On the testnet, run the agent-control proof script with a funded test account; its revoke step records each order's outcome, the network's own record of the revoke, the agent's orders on the book before it and which of them the network cancelled.

## Last run (UTC date)

15 Nov 2026 (orders in flight during a revoke, on the testnet)

## Verifier

`python3 verifiers/agent_control_proof.py`

## Result

An agent had three orders resting on the book, and six more of its orders were sent one after another while its owner revoked it. The network recorded the revoke at height 271,292,580 (record kind `agent_revoked`, 5 orders cancelled). The last order accepted was recorded at height 271,292,565; the first order refused was refused when received (answered at height 271,292,631; code bad_signature, session_key_mismatch), and so was every order after it. In the same step as the revoke, the network cancelled all five of the agent's open orders: the three that were resting and the two in-flight orders accepted before it. Each one's record says "agent revoked" at the revoke's height, and none of the agent's orders was on the book afterwards. An order signed by a revoked or replaced session key was refused, and an order that reused an order number was refused.

## Limits

One in-flight order was taken in before the revoke applied and then left no order, fill or refusal record; it did not trade, but the network does not yet say what became of it. The order cancellation on revoke runs on the testnet; it is not yet on mainnet. Expired sessions, expired agents and expired agent policies are not yet tested on a network.

Also on the docs: https://docs.vordium.com/security/ai-audit/#revoked-keys
