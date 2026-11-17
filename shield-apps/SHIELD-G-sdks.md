# SHIELD G — the Vordium SDKs (Python and JavaScript)

**Scope.** What the two published SDKs sign and send: the chain and genesis a signature is bound to, client nonces under
concurrency, crashes and a clock set back, resends after a lost answer, the signing bytes of every operation against the
official vectors and across the two SDKs, key files and key secrecy, rounding of sizes and prices, hostile market rules,
and whether the live test network accepts what the SDKs sign.
**Audited.** Python `vordium` 1.6.0 as published (commit dce6d79) and JavaScript `@vordium/sdk` 0.2.0 as published
(commit 714d2a1).
**Kit.** `kit/sdks/` (sha256 in SHA256SUMS). **Run:** 2026-11-17, the live checks with fresh throwaway test-network accounts.

**Vectors: 52** — covered 34 · by design 7 · open 11.

| Check | What it checks | Result |
|---|---|---|
| `c01_identity_py` | A local fake node claims a series of identities: another chain id, another genesis on either network, the main network when the client asked for the test network (and the reverse), a consistent main-network identity … | PASS |
| `c02_identity_js` | A local fake node claims a series of identities: another chain id, another genesis on either network, the main network when the client asked for the test network (and the reverse), a consistent main-network identity … | PASS |
| `c05_nonces_py` | Many processes and threads take client nonces for one account. All must be unique and rising, including after a `kill -9`, when the clock goes back one hour, and with 0700/0600 modes on the state files. | PASS |
| `c06_nonces_js` | Many processes and threads take client nonces for one account. All must be unique and rising, including after a `kill -9`, when the clock goes back one hour, and with 0700/0600 modes on the state files. | PASS |
| `c07_resend_py` | A fake node drops answers or replies 503. Every retry must carry the same signed bytes, at most three copies, and the result must be read back before it is reported. A cancel-all is never sent again after a lost … | PASS |
| `c08_resend_js` | A fake node drops answers or replies 503. Every retry must carry the same signed bytes, at most three copies, and the result must be read back before it is reported. A cancel-all is never sent again after a lost … | PASS |
| `c09_vectors_py` | The official agent-operation vectors in the public `Vordium/node` repository are reproduced, including signatures made by the SDK with the published test key. Every type string the network spec publishes equals the … | PASS |
| `c10_vectors_js` | The official agent-operation vectors in the public `Vordium/node` repository are reproduced, including signatures made by the SDK with the published test key. Every type string the network spec publishes equals the … | PASS |
| `c11_keys_py` | Key files are created 0600, never overwritten and never written through a symlink; a key file others can read is refused; the key never appears in an error, a repr, a DEBUG log or console output. | PASS |
| `c12_keys_js` | Key files are created 0600, never overwritten and never written through a symlink; a key file others can read is refused; the key never appears in an error, a repr, a DEBUG log or console output. | PASS |
| `c13_rounding_py` | About 8,000 sizes and prices on every live test-network market: a buy is never signed above the given price, a sell never below, a size never rounded up, and most values must be accepted so the check is not empty. … | PASS |
| `c14_rounding_js` | About 8,000 sizes and prices on every live test-network market: a buy is never signed above the given price, a sell never below, a size never rounded up, and most values must be accepted so the check is not empty. … | PASS |
| `c15_live_testnet_py` | Live test network, with a fresh account that is never funded. The chain applies the SDKs' SessionCreate, SessionRevoke, ScheduleCancel, RegisterAgentV2, RevokeAgent and ApproveBuilderFee signatures, judges a … | PASS |
| `c16_live_testnet_js` | Live test network, with a fresh account that is never funded. The chain applies the SDKs' SessionCreate, SessionRevoke, ScheduleCancel, RegisterAgentV2, RevokeAgent and ApproveBuilderFee signatures, judges a … | PASS |

**Open:**
- C-08: under work.
- C-09: under work.
- C-17b: under work.
- C-20b: under work.
- C-27: under work.
- C-31: under work.
- C-36: under work.
- C-37: under work.
- C-38: under work.
- C-39b: under work.
- C-40: under work.

**Re-run:** `cd kit/sdks/tests && npm install && PY=python3 node run-all.mjs ../my-run` (after `pip install "vordium==1.6.0"`
and `npm install @vordium/sdk@0.2.0`).
