# SHIELD H — the Vordex app: what you see is what you sign

**Scope.** Every signature the Vordex trading app asks a wallet (or its in-browser session key) to make, compared with
what the screen shows and with what the app sends: form fields against signed fields, the AI sign-in text and its
relay, deposit vault pins, framing and page headers.
**Audited.** The Vordex app release live on 2026-11-17 (commit 9b308a4).
**Kit.** `kit/app-signing/` (sha256 in SHA256SUMS). **Run:** 2026-11-17; source checks against the app source at that
commit; live checks read-only, or on the test network with throwaway accounts.

**Vectors: 45** — covered 21 · by design 9 · open 15.

| Check | What it checks | Result |
|---|---|---|
| `l01-frame-and-headers` | No other site can frame an app page (`frame-ancestors 'none'`, `X-Frame-Options: DENY`, an in-page guard). The trade widget, the one page made to be framed, signs nothing and is not served on the main network. HSTS is on and no script source is a wildcard. | PASS |
| `r01-relay-signin` | The AI sign-in refuses a look-alike origin, a text naming another domain, a forged nonce, another chain, a captured text redeemed with another device key, a reused nonce, a stolen token, and a replayed or moved request proof. | PASS |
| `u02-form-parity` | For each form, every signed field equals the field sent, and no unsigned field is sent, with 200 random inputs each. | PASS |
| `u04-siwe` | The sign-in text is rebuilt from the page's own facts and hostile variants are refused, including a look-alike host. | PASS |
| `u07-deposit-pins` | A vaults read naming another deposit vault is refused; a deposit approves exactly the amount, to the published vault. | PASS |

**Open:**
- D-03: under work.
- D-14: under work.
- D-18: under work.
- D-19: under work.
- D-23: under work.
- D-29: under work.
- D-30: under work.
- D-32: under work.
- D-35: under work.
- D-37: under work.
- D-38: under work.
- D-39: under work.
- D-41: under work.
- D-44: under work.
- D-45: under work.

**Re-run:** `cd kit/app-signing/tests && npm install && node run-all.mjs ../my-run /path/to/app-source`
