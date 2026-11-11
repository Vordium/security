# Your balance is counted in the reserves tree

**PROVED**

## Network

Testnet

## Code version

Af9d410728b6cbb2

## Check it yourself

Run the reserves verifier from the security repository (https://github.com/Vordium/security) with your address

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/verify_reserves.py`

## Result

An account's proof walks from its own leaf, its address and the amount owed to it, up to the root published in the coverage answer. An account with no balance is reported as not in the tree.

## Limits

It shows that your balance is included, not that the published total is right.

Also on the docs: https://docs.vordium.com/security/ai-audit/#reserves-inclusion
