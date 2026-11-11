# A batch is committed in two steps that faults cannot split

**PROVED**

## Network

A local test network

## Code version

The candidate build d236e67bc4fa21d8; mainnet runs the same commit rules

## Check it yourself

Run by the team

## Last run (UTC date)

30 Sep 2026

## Result

99 runs under faults: no conflicting certificates, no split, no halt and no divergence of state; every commit-rule check passed, and switching off any one rule was caught.

## Limits

Run on the candidate build, not on the released binary.
