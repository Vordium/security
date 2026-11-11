# One tap stops everything

**BUILT, NOT PROVEN**

## Network

Local test; testnet for the network stop

## Code version

Vordex app release v157

## Check it yourself

In Vordex → AI or Agents, **Stop everything now**; the card then lists what the network shows as stopped, or names anything still live.

## Last run (UTC date)

11 Nov 2026

## Result

One tap disconnects every AI, cancels your open orders, and stops your trading key and every agent; the page says "stopped" only when the network shows no session, no live agent and no open order. Its tests pass.

## Limits

The whole tap has not yet been run end to end on a network; its network stop is proven above. On your own computer, `stop_all` in the MCP server stops only that program; an AI connected to it can call `stop_all` itself, so text that misleads the AI can pause it and cancel your resting orders.

Also on the docs: https://docs.vordium.com/security/ai-audit/#stop-everything
