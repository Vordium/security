# A public state checkpoint is signed by the validators and tied to the chain

**PROVED**

## Network

Testnet

## Code version

Af9d410728b6cbb2

## Check it yourself

Run the state-checkpoint verifier from the security repository (https://github.com/Vordium/security)

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/verify_state_checkpoint.py`

## Result

For the checkpoint at batch 13,575,328, the file's length and hash match; every seated validator's signature on its state root is valid, more than the required share; its head block is the public block and is in that batch's signed record. A changed bit in the root or a signature is refused.

## Limits

The signatures are checked against the validators seated now. This check alone does not recompute the root.

Also on the docs: https://docs.vordium.com/security/ai-audit/#state-checkpoint
