# A failed read is never shown as "no position"

**BUILT, NOT PROVEN**

## Network

Vordex app

## Code version

App release v155 and later

## Check it yourself

Run by the team

## Last run (UTC date)

At each release (source checks)

## Result

When your positions cannot be read, the trading page says "Positions not read" with the time and a **Retry** button, instead of showing no positions. Portfolio and vaults show a read error the same way.

## Limits

The browser test that makes the network fail has not yet been run on the current release, and it is not yet scheduled. The agents dashboard keeps showing "Reading…" when its read fails.

Also on the docs: https://docs.vordium.com/security/ai-audit/#failed-read
