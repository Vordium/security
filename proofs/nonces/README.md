# Order numbers stay unique across devices

**BUILT, NOT PROVEN**

## Network

Local test; testnet for the network's refusal

## Code version

The Python, JavaScript and MCP package code as of 10 Nov 2026

## Check it yourself

Run by the team

## Last run (UTC date)

10 Nov 2026 (packages); 9 Nov 2026 (testnet)

## Result

Each package gives every signed request a number higher than the last one on that computer, also when the clock moves back, and the tests pass. The testnet refuses a number that was already used.

## Limits

One account signing from two computers at once, or with clocks that disagree, is not yet tested.

Also on the docs: https://docs.vordium.com/security/ai-audit/#nonces
