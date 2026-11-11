# Market data cannot steer your AI into an order you did not want

**MISSING OR FAILING**

## Network

Local test; testnet end-to-end run

## Code version

The Vordex testnet app before release v156

## Check it yourself

Run by the team

## Last run (UTC date)

5 Nov 2026

## Result

In **I approve each order**, every order your AI proposes is shown on your device and the order signed must be exactly the order proposed; each approval works once; when no device of yours is open, no request is made. Proposals are off on mainnet. An end-to-end run on the testnet passed 30 of 30 checks.

## Limits

No test yet plants an instruction in market or agent data and checks what your AI then proposes. Text in data can reach your AI as if it were an instruction. Some AI apps accept their own confirmation prompts without asking you. On the testnet, **Auto within limits** approves any proposal that fits your agent's limits without asking a person, so your limits are the only bound. The end-to-end run has not yet been repeated on app release v156.

Also on the docs: https://docs.vordium.com/security/ai-audit/#planted-data
