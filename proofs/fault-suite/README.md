# The network keeps one history under faults

**PROVED**

## Network

A local test network

## Code version

The test build of node release af9d410728b6cbb2, with fault injection

## Check it yourself

Run by the team

## Last run (UTC date)

11 Nov 2026

## Result

With the new consensus rules switched on, 54 of 54 runs passed across 16 fault scenarios: network partitions, validators down, a storm of leader changes, a leader that signs two versions, tampered messages, slow and restarting validators, mixed versions and state sync. No two conflicting certificates, no split, no halt and no crash; 23,454 batches finalized, 2,639 of them after a leader change. With the new rules switched off, a quick set of 8 runs also passed.

## Limits

A local test network, not a live one. Fault injection exists only in the test build. On the testnet these rules are not yet switched on.
