# Vordex app: what you see is what you sign — re-run kit

These checks test the Vordex trading app's signing screens. Every signature the app asks a wallet (or its in-browser
session key) to make is compared with what the screen shows and with what the app sends to the network.
Each check exits **0** when the defence holds, **1** when it does not, and **3** when it cannot run.

`vectors-public.json` lists each case, its status and the checks that cover it. A case is `covered` only when a check
sends or renders something and the defence holds.

## What you need

- Node.js 20 or later.
- `npm install` in `tests/`. This installs `ethers` and `playwright-core`.
- For browser checks, a Chromium or Chrome build. Pass its path as `--chrome PATH` or in `CHROME_PATH`.
- For source checks, a copy of the app source (`--app DIR`).

Nothing here needs a funded account. Every account and key is created fresh for the run and then thrown away.
Browser checks answer every write themselves, so nothing they capture reaches the network; checks that talk to the test
network use throwaway accounts only.

## The checks

| Check | Kind | What it checks |
|---|---|---|
| `l01-frame-and-headers.mjs` | live, read-only | No other site can frame an app page (`frame-ancestors 'none'`, `X-Frame-Options: DENY`, an in-page guard). The trade widget, the one page made to be framed, signs nothing and is not served on the main network. HSTS is on and no script source is a wildcard. |
| `r01-relay-signin.mjs` | live, test network | The AI sign-in refuses a look-alike origin, a text naming another domain, a forged nonce, another chain, a captured text redeemed with another device key, a reused nonce, a stolen token, and a replayed or moved request proof. |
| `u02-form-parity.mjs` | source, run | For each form, every signed field equals the field sent, and no unsigned field is sent, with 200 random inputs each. |
| `u04-siwe.mjs` | source, run | The sign-in text is rebuilt from the page's own facts and hostile variants are refused, including a look-alike host. |
| `u07-deposit-pins.mjs` | source, run | A vaults read naming another deposit vault is refused; a deposit approves exactly the amount, to the published vault. |

## Running

```
cd tests && npm install
node run-all.mjs ../my-run [/path/to/app-source]      # every check in this folder; one log per check + summary.txt
```

Any one check runs on its own with `node <check>.mjs` and the arguments its header names (`--out DIR`, `--app DIR`,
`--chrome PATH`, `--base URL`). Use a fresh output folder for every run.

## Reading the results

Each check prints one `PASS` or `FAIL` line per claim, then `<check>: N pass, M fail`. A browser check's `FAIL` names its
flow letter and quotes what the screen showed or what was signed. Its output folder keeps a screenshot of each flow,
plus `record.json` with every signature request and every captured request.
