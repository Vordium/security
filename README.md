# Vordium security

This repository lists what is proven about the protections around Vordium — the network, the Vordex app, the SDKs and
the hosted AI server — and how to re-run each check yourself. It is the **Vordium Security Proofs**.

The items about trading, keys, the AI server, sign-in, the websites and the chain data are also on the docs, with the
same words: https://docs.vordium.com/security/proofs/. The tests of the network itself are listed here.

## How to read it

Every item has exactly one status:

- **PROVED** — every part of the item has been shown to hold by a test on the network named.
- **BUILT, NOT PROVEN** — the protection is in place and parts of it are tested, but not every part has been shown to
  hold. What is proven is under *Result*; what is not, under *Limits*.
- **MISSING OR FAILING** — there is no test for it yet, or a test shows it does not hold today.

Each item names the network it was tested on, the code version where one is recorded, the date of the last run (UTC),
the result and its limits. "Local test" means the code was tested on its own, against a stand-in for the network.

Today: 43 items — 22 proved, 19 built but not proven, 2 missing or failing.

## Items

| Item | Status | Network | Last run |
| --- | --- | --- | --- |
| [Agent limits are enforced by the network](proofs/agent-limits/README.md) | BUILT, NOT PROVEN | testnet | 13 Nov 2026 (public agent-control proof on the testnet, daily loss included); 5 Nov 2026 (1,000 orders compared with the pre-trade check) |
| [Two agents cannot overspend one account](proofs/shared-collateral/README.md) | PROVED | testnet | 11 Nov 2026 |
| [A revoked agent or session key cannot trade](proofs/revoked-keys/README.md) | BUILT, NOT PROVEN | testnet; local test for the AI server | 15 Nov 2026 (orders in flight during a revoke, on the testnet) |
| [The network stop ends every signer at once](proofs/stop-signers/README.md) | PROVED | testnet | 11 Nov 2026 |
| [One tap stops everything](proofs/stop-everything/README.md) | BUILT, NOT PROVEN | local test; testnet for the network stop | 11 Nov 2026 |
| [Order numbers stay unique across devices](proofs/nonces/README.md) | BUILT, NOT PROVEN | local test; testnet for the network's refusal | 10 Nov 2026 (packages); 9 Nov 2026 (testnet) |
| [A lost answer never becomes a duplicate order](proofs/lost-answer/README.md) | BUILT, NOT PROVEN | local test | 11 Nov 2026 |
| [Keys stored in your browser cannot be copied out](proofs/browser-keys/README.md) | BUILT, NOT PROVEN | testnet | 10 Nov 2026 |
| [The hosted AI server withstands floods and crafted input](proofs/hosted-server/README.md) | BUILT, NOT PROVEN | testnet and mainnet (hosted server); local test | 13 Nov 2026 (testnet: tools listed, order request, text handling); 10 Nov 2026 (testnet); 9 Nov 2026 (mainnet) |
| [Market data cannot steer your AI into an order you did not want](proofs/planted-data/README.md) | BUILT, NOT PROVEN | local test; testnet end-to-end run | 13 Nov 2026 (local AI server, testnet) |
| [Signing in from a look-alike site is refused](proofs/phishing/README.md) | BUILT, NOT PROVEN | testnet; a test copy of the mainnet setup | 10 Nov 2026 |
| [App fees on perpetual markets are charged only as approved and add up](proofs/builder-fees/README.md) | PROVED | testnet, perpetual markets | 14 Nov 2026 |
| [Our domains cannot be quietly redirected](proofs/domains/README.md) | BUILT, NOT PROVEN | websites | checked every day |
| [Changes reach the live sites only through the release process](proofs/releases/README.md) | BUILT, NOT PROVEN | release process | 10 Nov 2026 |
| [Private data does not appear on public pages](proofs/private-data/README.md) | BUILT, NOT PROVEN | websites | checked every day |
| [Domain names and version numbers in the docs are current](proofs/current-text/README.md) | BUILT, NOT PROVEN | docs websites | checked every day |
| [A failed read is never shown as "no position"](proofs/failed-read/README.md) | BUILT, NOT PROVEN | Vordex app | at each release (source checks) |
| [Your pending AI proposals are not visible to others](proofs/pending-proposals/README.md) | PROVED | testnet | 11 Nov 2026 |
| [Impostor sites and fake tokens are spotted](proofs/impostors/README.md) | BUILT, NOT PROVEN | websites | checked every day |
| [Blocks link to each other and match what the validators signed](proofs/block-links/README.md) | PROVED | mainnet and testnet | 11 Nov 2026 |
| [A public state checkpoint is signed by the validators and tied to the chain](proofs/state-checkpoint/README.md) | PROVED | testnet | 11 Nov 2026 |
| [The state root can be recomputed from the public checkpoint](proofs/state-root/README.md) | PROVED | testnet | 11 Nov 2026 |
| [A new node started from public state files reaches the tip with the same root](proofs/fresh-node/README.md) | PROVED | testnet | 25 Oct 2026 |
| [The bridge vaults hold what the reserves answer says](proofs/reserves-coverage/README.md) | PROVED | testnet | 11 Nov 2026 |
| [Your balance is counted in the reserves tree](proofs/reserves-inclusion/README.md) | PROVED | testnet | 11 Nov 2026 |
| [Proof of reserves with per-account proofs on mainnet](proofs/reserves-mainnet/README.md) | MISSING OR FAILING | mainnet | — |
| [Each batch's trading records match its published digest](proofs/records-digest/README.md) | PROVED | testnet | 11 Nov 2026 |
| [Each block's order of operations matches its published digest](proofs/op-order/README.md) | PROVED | testnet | 11 Nov 2026 |
| [The explorer shows the blocks the validators signed](proofs/explorer-hashes/README.md) | PROVED | testnet | 11 Nov 2026 |
| [The network keeps one history under faults](proofs/fault-suite/README.md) | PROVED | a local test network | 11 Nov 2026 |
| [A batch is committed in two steps that faults cannot split](proofs/batch-commit/README.md) | PROVED | a local test network | 30 Sep 2026 |
| [No two conflicting certificates on mainnet](proofs/double-certificates/README.md) | PROVED | mainnet | 29 Sep 2026 |
| [Every release passes the full test gate](proofs/release-tests/README.md) | PROVED | build | 11 Nov 2026 |
| [The release builds the same bytes twice](proofs/reproducible-build/README.md) | PROVED | build | 11 Nov 2026 |
| [Tests catch deliberate changes to the consensus rules](proofs/mutation-tests/README.md) | PROVED | build | 11 Nov 2026 14:00–21:43 UTC, follow-up 12 Nov 2026 10:58 UTC |
| [Continuous fuzzing](proofs/fuzzing/README.md) | MISSING OR FAILING | build | ongoing |
| [Your trading key and your agents trade side by side](proofs/parallel-signers/README.md) | BUILT, NOT PROVEN | build | 11 Nov 2026 |
| [Liquidation in steps, then backstop, insurance fund and auto-deleverage](proofs/liquidation-model/README.md) | BUILT, NOT PROVEN | a local test network | 7 Nov 2026 |
| [The read-only order check agrees with the network](proofs/order-check/README.md) | BUILT, NOT PROVEN | a local test network | 6 Nov 2026 |
| [A data-provider outage holds bridge deposits and payouts, then settles each exactly once](proofs/bridge-outage/README.md) | BUILT, NOT PROVEN | testnet | 18 Nov 2026 (one then both data endpoints unreachable, 18 minutes each) |
| [Finality as a public reader sees it](proofs/finality-public/README.md) | PROVED | mainnet and testnet | 11 Nov 2026 |
| [Balances follow the public records on the testnet](proofs/money-replay/README.md) | PROVED | testnet | 16 Nov 2026 14:37–15:22 UTC (heights 285,325,095 to 285,723,367) |
| [Each balance record adds up from the money records it names, on the testnet](proofs/balance-replay/README.md) | PROVED | testnet | 18 Nov 2026 (heights 300,000,000 to 300,176,327) |

Each link opens `proofs/<item>/README.md`, with the full result and limits.

## Re-run the checks

The scripts in `verifiers/` read public addresses only. They need Python 3 and nothing else, except `verify_state_checkpoint.py`, which needs one keccak-256 library
(`pycryptodome` or `eth-hash`). `keccak.py` and `_common.py` are shared helpers that sit beside the scripts; most
scripts take `--plant…`, which plants a fault so you can see the check fail.

```bash
git clone https://github.com/Vordium/security
cd security
python3 verifiers/check_site_headers.py        # every official site tells browsers to use only secure connections
python3 verifiers/check_hosted_ai_server.py    # the hosted AI server is read-only and publishes its request limits
python3 verifiers/verify_block_links.py --network mainnet --batches 20   # blocks link up and match the signed batches
python3 verifiers/finality_probe.py --network mainnet --seconds 60       # how soon a batch is final, seen from outside
python3 verifiers/verify_reserves.py coverage            # the bridge vaults hold what the reserves answer says (testnet)
python3 verifiers/verify_reserves.py proof 0xYourAddress  # your balance is counted in the reserves tree (testnet)
python3 verifiers/verify_records_digest.py               # a batch's trading records match its published digest (testnet)
python3 verifiers/verify_op_order.py                     # each block's order of operations matches its digest (testnet)
pip install pycryptodome
python3 verifiers/verify_state_checkpoint.py   # a public state checkpoint: file, validator signatures, chain link
```

Each script prints one line per check and exits 0 when every check passes. Items marked "run by the team" were run by the
Vordium team and need private test accounts; their result and limits are recorded in `proofs/`.

## SHIELD: accounting, reserves, explorer and finalized history

`shield/` holds four reports and the kit that produced them:

- accounting replay;
- reserves;
- explorer truth;
- one finalized history.

Each report states its scope, its checks with their results on each network, and its open items. Its last line is the
command that re-runs it.

The kit reads public addresses only and needs Python 3 and nothing else. `shield/kit/README.md` explains each script
and its result words (`PASS`, `FAIL`, `INCOMPLETE`).

`shield/results.json` pins every report and kit file by sha256, and is signed with the same release key
(`shield/results.json.asc`):

```bash
cd shield
sha256sum -c SHA256SUMS
gpg --verify results.json.asc results.json
```

## SHIELD: agent controls, AI server, SDKs and app signing

`shield-apps/` holds four reports and the kit that produced them:

- agent controls;
- the AI server;
- the SDKs;
- the app's signing screens.

Each report names the exact published version it checked, its checks with their results, and its open items. Its last
line is the command that re-runs it.

`shield-apps/results.json` pins every report and kit file by sha256, and is signed with the same release key
(`shield-apps/results.json.asc`):

```bash
cd shield-apps
sha256sum -c SHA256SUMS
gpg --verify results.json.asc results.json
```

## Check the signature

`results.json` holds every item in one file. It is signed with the Vordium release key, the same key that signs the
network's releases. The signature is `results.json.asc`; the public key is `release-key.asc` in this repository (the same key as
`pub_key.asc` in https://github.com/Vordium/node), fingerprint `C5EB 4728 F660 369C E519  D834 B48F B4B7 1EFD 48AE`.

```bash
sha256sum results.json
# 8ab4ce3373f6fa722f4f11cfb92ac02f1008328bc140b1db971b21289d5c9ebd  results.json
gpg --import release-key.asc
gpg --verify results.json.asc results.json
```

`gpg --verify` must say "Good signature" from the key with the fingerprint above.

## Report a vulnerability

See [SECURITY.md](SECURITY.md).

List date: 2026-11-18.
