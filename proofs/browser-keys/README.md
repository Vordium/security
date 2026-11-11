# Keys stored in your browser cannot be copied out

**BUILT, NOT PROVEN**

## Network

Testnet

## Code version

The Vordex testnet app on the run date

## Check it yourself

Run by the team; what the seal protects is described in Session Keys (https://docs.vordium.com/guides/session-keys)

## Last run (UTC date)

10 Nov 2026

## Result

The device key cannot be exported from the browser: a browser test passed 25 of 25 checks. The trading key is stored only sealed under a key the browser keeps non-extractable.

## Limits

Code running on the site itself can use the trading key and the agent key; the site's content security policy is what keeps other code out, and it is not covered by this audit. A copy of the whole browser profile carries the browser's key with it. No test yet runs an injected script or a browser extension against the keys.

Also on the docs: https://docs.vordium.com/security/ai-audit/#browser-keys
