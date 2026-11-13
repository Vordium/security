# The hosted AI server withstands floods and crafted input

**BUILT, NOT PROVEN**

## Network

Testnet and mainnet (hosted server); local test

## Code version

The release the hosted server reports in the `version` field of `https://mcp.vordium.com/mainnet/health` and `https://mcp.vordium.com/testnet/health`

## Check it yourself

`curl -s https://mcp.vordium.com/testnet/health` shows the server's request limits and counters; the agent-control proof script (step 8) lists the hosted server's tools and asks it for an order.

## Last run (UTC date)

13 Nov 2026 (testnet: tools listed, order request, text handling); 10 Nov 2026 (testnet); 9 Nov 2026 (mainnet)

## Verifier

`python3 verifiers/check_hosted_ai_server.py`

## Result

Long or crafted text in a request cannot stall the server; request size and per-client rates are capped, and their tests pass. The MCP Inspector checks pass 26 of 26 on both networks. The hosted testnet server lists no tool that signs or sends an order, refuses an order request by name, and marks the text in its results as data from the network, never instructions.

## Limits

The hosted mainnet server has not yet been checked for how it marks text from the network. No flood test has been recorded against the hosted server.

Also on the docs: https://docs.vordium.com/security/ai-audit/#hosted-server
