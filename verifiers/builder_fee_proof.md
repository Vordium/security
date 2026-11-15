# Builder-fee proof (Vordium testnet)

An app or bot (the **builder**) can add its own fee to the orders it sends for a trader. The trader first approves the
builder up to a rate; every order that names the builder carries its fee; the chain charges it on each fill and keeps
it for the builder until the builder claims it.

This proof shows how the chain charges and accounts for that fee at its edges. You can rerun it with public tools only:

- the Vordium Python SDK (`vordium` on PyPI),
- the public test network endpoints (`https://testnet.vordex.xyz/chain`, `https://testnet.vordex.xyz/network-spec.json`).

**Test network only.** The script refuses any network other than the Vordium testnet (chain id 101102). Testnet
tokens have no value.

## Units

Builder fees are in **cbps**, hundredths of a basis point: 1 cbps = 0.0001 %, 500 cbps = 0.05 %, 1,000 cbps = 0.1 %.
Amounts are USDC with 6 decimals (`_6dec`): 1 unit = 0.000001 USDC. The fee on a fill is

    fill value (price x size) x rate (cbps) / 1,000,000

## What each case proves

| Case | What happens | What it proves |
|---|---|---|
| a | One builder-fee order fills in two or more fills: as taker (one buy takes two resting sells) and as maker (one resting sell is taken in two pieces). | Every fill record carries its own builder fee (key `builder`: `taker_builder`, `taker_fee_6dec`, `maker_builder`, `maker_fee_6dec`), and the fills add up to exactly what the builder's stats read moved by. |
| b | The smallest fee (1 cbps) on the smallest order the market takes, then on a fill of one size step, worth a fraction of one USDC. Also: a market order of one size step. | Each fill's charged fee against its exact value; how a fee below one 6-decimal unit is charged. |
| c | The trader approves a rate X. Orders at X + 1, at 0, and above the market's cap; then an order at exactly X that fills. | The approved rate is a hard ceiling: the chain refuses each one over it with its code, and charges an order at X exactly X. |
| d | The trader approves the most builders it may, then one more. An approved builder that holds no funds is named on an order. The approval's fields are listed. | The approval count has a maximum and the next approval is refused; an approval is a rate cap, not a budget (it carries no amount). |
| e | A builder-fee order rests on the book; the trader then withdraws the approval (and, in a second run, lowers it). Another account then fills the resting order. | What the chain charges on a fill made after the approval changed, and whether a new order naming the builder is still accepted. |
| f | The builder claims its fees at the end. | The fees of every fill in the run equal the change in claimed + unclaimed; after the claim, fees = claimed + unclaimed still holds, claimed rose by exactly the unclaimed amount, and the builder's balance rose by the same amount. |

Before any case, the script reads the chain's published refusal codes (`GET /orders/codes`, list
`builder_refusal_codes`). Every refusal is recorded verbatim with the chain's code.

Refusal probes (c, d) are signed with the SDK's own signer and sent as signed, skipping the SDK's checks before
signing, so the record shows the **chain's** answer. The SDK's own verdict is recorded beside it.

## Accounts

- **trader**: approves the builder and places the builder-fee orders.
- **builder**: named on those orders. It also places the plain counter-orders that fill the trader's resting orders,
  and claims its fees at the end. The chain refuses orders that name a builder whose account value is below its
  minimum (`min_account_value_6dec` in `GET /builder/stats/<address>`, 100 USDC today).
- **fillers** (case d only): up to 10 extra builder addresses. An approval needs no funds on the builder, so these hold
  nothing; the script makes their keys on first use.

## Rerun it

```bash
python3 -m venv venv
venv/bin/pip install -r builder_fee_requirements.txt

# two fresh keys (mode 600; only the addresses are printed)
venv/bin/python builder_fee_proof.py --make-keys ./keys
```

Claim test USDC at <https://testnet.vordex.xyz/faucet> to **both** trading accounts (the trader needs at least 50
USDC; the builder at least 100 USDC). Then check both accounts (nothing is signed or sent):

```bash
venv/bin/python builder_fee_proof.py --trader-key-file keys/trader.key --builder-key-file keys/builder.key \
  --filler-key-dir keys/fillers
```

and run it on the test network:

```bash
venv/bin/python builder_fee_proof.py --trader-key-file keys/trader.key --builder-key-file keys/builder.key \
  --filler-key-dir keys/fillers --live
```

At the end the script cancels the resting orders of both accounts, closes their positions with reduce-only orders and
withdraws every approval it made.

Each run writes a folder `proof-<UTC time>/` (or `--out DIR`, which must be new or empty) with:

- `results.json`: every case with its status, heights, order and fill ids, amounts, the chain's answers verbatim and
  the signed bodies (signatures shortened);
- `console.log`: the run as it was printed.

### Options

| Option | Default | Meaning |
|---|---|---|
| `--market` | ETH | the market used |
| `--leverage` | 2 | leverage of every order |
| `--fee-a` | 500 | builder fee in case a (cbps) |
| `--fee-c` | 300 | approved rate in case c (cbps) |
| `--fee-e` | 400 | builder fee in case e (cbps) |
| `--min-usdc` | 50 | test USDC each account must have available |
| `--only` | a,b,c,d,e,f | run only some cases (f always claims) |

The book on the test network moves. A case that needs the book to stay still for a moment records what happened and
why when it does not; run it again for a fresh try.
