# A lost answer never becomes a duplicate order

**BUILT, NOT PROVEN**

## Network

Local test

## Code version

Vordex app release v157; Python package 1.4.10, JavaScript package 0.1.3, MCP server 0.6.3

## Check it yourself

Run by the team

## Last run (UTC date)

11 Nov 2026

## Result

When the answer to a request is lost, the app and the packages send the same signed request again at most once, never a new one, and treat it as unknown until they read it back from the network. In the app the order shows **Checking…**, then **Unknown — not resent** until the network shows what happened. The tests pass.

## Limits

A resend of the same request has not yet been run against a network. The network applies an identical cancel, or an identical take-profit or stop-loss change, each time it is sent.

Also on the docs: https://docs.vordium.com/security/ai-audit/#lost-answer
