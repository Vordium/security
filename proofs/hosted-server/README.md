# The hosted AI server withstands floods and crafted input

**BUILT, NOT PROVEN**

## Network

Testnet and mainnet (hosted server); local test

## Code version

The release the hosted server reports in the `version` field of `https://mcp.vordium.com/mainnet/health` and `https://mcp.vordium.com/testnet/health`

## Check it yourself

`curl -s https://mcp.vordium.com/testnet/health` shows the server's request limits and counters.

## Last run (UTC date)

10 Nov 2026 (testnet); 9 Nov 2026 (mainnet)

## Verifier

`python3 verifiers/check_hosted_ai_server.py`

## Result

Long or crafted text in a request cannot stall the server; request size and per-client rates are capped, and their tests pass. The MCP Inspector checks pass 26 of 26 on both networks.

## Limits

Text inside tool results is passed to your AI as it is; the server does not yet tell your AI that such text is data and never an instruction. No flood test has been recorded against the hosted server.

Also on the docs: https://docs.vordium.com/security/ai-audit/#hosted-server
