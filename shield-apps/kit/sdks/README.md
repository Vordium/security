# SDK signing checks: re-run kit

These checks test the Python package `vordium` and the JavaScript package `@vordium/sdk` from the outside. They cover:

- which chain and genesis a signature is bound to;
- client nonces under concurrency, a crash and a clock set back;
- retries after a lost answer;
- the signing bytes of every operation, against the official vectors and across the two SDKs;
- key files and key secrecy;
- rounding of sizes and prices, and hostile market rules;
- whether the live test network accepts what the SDKs sign.

Each check is a small script that anyone can run with public tools. Most need no network. Every script ends with one
line and an exit code:

| Exit | Meaning |
|---|---|
| 0 | `DEFENDED`: every check in the script holds. |
| 1 | A check failed; the line names it. |
| 3 | `CANNOT RUN`: for example, the package is missing or the network cannot be reached. |

`vectors-public.json` lists what this kit covers, with the status of each item.

## Setup

```
python3 -m venv venv && . venv/bin/activate
pip install vordium
cd tests && npm install          # installs @vordium/sdk and ethers from package.json
```

You need Python 3.8 or newer and Node 20 or newer. The checks make their keys in memory and never print or store them.
Nonce marks go to a temporary folder.

## Run

```
cd tests
PY=python3 node run-all.mjs ../my-run              # every check, including the live test-network ones
PY=python3 node run-all.mjs ../my-run --offline    # no live test-network calls
PY=python3 node run-all.mjs ../my-run c01 c13      # only the checks whose file name starts with c01 or c13
```

`my-run/summary.tsv` lists each check with its exit code; each check's output is in its own log there. Python checks
end in `_py`, JavaScript checks in `_js`.

## What the checks cover

| Checks | Covers |
|---|---|
| c01 (Python), c02 (JS) | A local fake node claims a series of identities: another chain id, another genesis on either network, the main network when the client asked for the test network (and the reverse), a consistent main-network identity on an unnamed address, malformed values, and a genesis that changes after the first order. The real test-network identity must be signed for; every other identity must be refused before anything is signed or sent. |
| c05 (Python), c06 (JS) | Many processes and threads take client nonces for one account. All must be unique and rising, including after a `kill -9`, when the clock goes back one hour, and with 0700/0600 modes on the state files. |
| c07 (Python), c08 (JS) | A fake node drops answers or replies 503. Every retry must carry the same signed bytes, at most three copies, and the result must be read back before it is reported. A cancel-all is never sent again after a lost answer. A new call takes a new nonce. |
| c09 (Python), c10 (JS) | The official agent-operation vectors in the public `Vordium/node` repository are reproduced, including signatures made by the SDK with the published test key. Every type string the network spec publishes equals the SDK's, and the check fails if none can be compared. Both SDKs give identical digests for every operation in `testnet-signing-vectors.json`. No two operations share a field list. |
| c11 (Python), c12 (JS) | Key files are created 0600, never overwritten and never written through a symlink; a key file others can read is refused; the key never appears in an error, a repr, a DEBUG log or console output. |
| c13 (Python), c14 (JS) | About 8,000 sizes and prices on every live test-network market: a buy is never signed above the given price, a sell never below, a size never rounded up, and most values must be accepted so the check is not empty. Hostile market rules are refused or rounded the safe way, while the published rules still sign. Each posted body equals what was signed. |
| c15 (Python), c16 (JS) | Live test network, with a fresh account that is never funded. The chain applies the SDKs' SessionCreate, SessionRevoke, ScheduleCancel, RegisterAgentV2, RevokeAgent and ApproveBuilderFee signatures, judges a PlaceOrder on the account's balance rather than its signature, and refuses the same order and cancel signed for the main network's domain. |

## The vector file

`tests/testnet-signing-vectors.json` holds one vector for each of the 22 operations the JavaScript SDK signs, in the
test network's domains (chain 101102). Each vector carries the type string and type hash, a sample message, the digest
and a signature by a public test key (its private key is sha256 of the label in the file; never funded).
`make-testnet-vectors.mjs` rebuilds it; c10 then compares the JavaScript SDK with it and c09 the Python SDK.
