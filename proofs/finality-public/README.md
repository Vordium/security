# Finality as a public reader sees it

**PROVED**

## Network

Mainnet and testnet

## Code version

Mainnet 19a4a7a68365d17e; testnet af9d410728b6cbb2

## Check it yourself

`python3 verifiers/finality_probe.py --network mainnet --seconds 60` (and `--network testnet`)

## Last run (UTC date)

11 Nov 2026

## Verifier

`python3 verifiers/finality_probe.py`

## Result

Over 60 seconds on mainnet, 142 batches: half were final and readable within 977 ms, 99 in 100 within 1,477 ms. On the testnet, 190 batches: 1,807 ms and 4,380 ms. See How Vordium reaches finality (https://docs.vordium.com/guides/finality).

## Limits

An upper bound: it includes public caching, the network path and up to 100 ms of polling. Answers without a block time are skipped. One 60-second window without faults.
