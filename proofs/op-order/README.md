# Each block's order of operations matches its published digest

**PROVED**

## Network

Testnet

## Code version

Af9d410728b6cbb2

## Check it yourself

Run the operation-order verifier from the security repository (https://github.com/Vordium/security)

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/verify_op_order.py`

## Result

For recent blocks, the digest of the operations' hashes in block order equals the block's published digest, and a second public endpoint serves the same hashes and digest. Swapping two operations is caught.

## Limits

Each operation's own hash is not recomputed here.

Also on the docs: https://docs.vordium.com/security/ai-audit/#op-order
