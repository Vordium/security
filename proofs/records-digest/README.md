# Each batch's trading records match its published digest

**PROVED**

## Network

Testnet

## Code version

Af9d410728b6cbb2

## Check it yourself

Run the records-digest verifier from the security repository (https://github.com/Vordium/security)

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/verify_records_digest.py`

## Result

The digest recomputed from the public trading records of a batch equals the digest the network publishes for it; changing one record makes them differ.

## Limits

—

Also on the docs: https://docs.vordium.com/security/ai-audit/#records-digest
