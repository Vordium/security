# The state root can be recomputed from the public checkpoint

**PROVED**

## Network

Testnet

## Code version

Af9d410728b6cbb2

## Check it yourself

The state-checkpoint verifier from the security repository (https://github.com/Vordium/security), given the node's verifier program and the testnet genesis file

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/verify_state_checkpoint.py`

## Result

The same checkpoint was decoded and its Merkle root recomputed; it equals the published root `104a359c…dddea46`.

## Limits

It needs the verifier program built from the node source and the testnet genesis file, and neither is published as a download yet, so outsiders cannot run it yet. Four fields are published as hashes only.

Also on the docs: https://docs.vordium.com/security/ai-audit/#state-root
