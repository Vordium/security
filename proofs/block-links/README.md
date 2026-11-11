# Blocks link to each other and match what the validators signed

**PROVED**

## Network

Mainnet and testnet

## Code version

Mainnet 19a4a7a68365d17e; testnet af9d410728b6cbb2

## Check it yourself

Run the block-link verifier from the security repository (https://github.com/Vordium/security) on mainnet or the testnet

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/verify_block_links.py`

## Result

On each network, 20 batches and 140 blocks checked with no failure: the validators' signed record of each batch lists exactly the block hashes the network serves, and every block builds on the last block of the batch before.

## Limits

It does not recompute block hashes or check the validators' signatures, and it trusts what the public endpoint serves.

Also on the docs: https://docs.vordium.com/security/ai-audit/#block-links
