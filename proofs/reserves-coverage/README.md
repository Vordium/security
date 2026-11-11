# The bridge vaults hold what the reserves answer says

**PROVED**

## Network

Testnet

## Code version

Af9d410728b6cbb2

## Check it yourself

Run the reserves verifier from the security repository (https://github.com/Vordium/security)

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/verify_reserves.py`

## Result

Each vault's USDC, read from a public Arbitrum Sepolia endpoint at the block the answer names, adds up to the answer's vault USDC to the unit (1,961,493.601017 USDC); the coverage ratio is held divided by owed (5.540247); the answer says covered only when the USDC held is at least what is owed. A planted difference of one unit is caught.

## Limits

The adjustments inside the USDC held, for deposits not yet credited and payouts not yet settled, are the network's own figures and are not recomputed. See Proof of reserves (https://docs.vordium.com/security/reserves).

Also on the docs: https://docs.vordium.com/security/ai-audit/#reserves-coverage
