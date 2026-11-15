# App fees on perpetual markets are charged only as approved and add up

**PROVED**

## Network

Testnet, perpetual markets

## Code version

The testnet network on the run date

## Check it yourself

On the testnet, with two funded test accounts, run the public builder-fee proof with the Vordium Python SDK: it approves an app, places orders that name it, fills them and claims the fees, and writes every answer of the network to a results file.

## Last run (UTC date)

14 Nov 2026

## Verifier

`python3 verifiers/builder_fee_proof.py`

## Result

An app can add its own fee to a trader's orders only up to the rate the trader approved. The network accepted an order at exactly the approved rate and charged that rate, and refused an order one step above it, an order with a fee of zero and an order above the market's cap, each with its own code. An account may approve at most 10 apps; the next approval was refused, and an approval is a rate limit with no amount or budget. An order naming an app with no funds was refused (builder_too_small); the network's published minimum is 100 USDC. When the trader withdrew an approval, or lowered it below a resting order's fee, that order paid no app fee when it filled later; after the approval was withdrawn, new orders naming the app were refused (code builder_not_approved). On every fill the fee was the fill's value times the rate, rounded up to the next 0.000001 USDC, so a fee worth less than 0.000001 USDC is charged as 0.000001 USDC. The fees on all fills added up exactly to the app's total; after the app claimed them, its claimed amount and its balance rose by exactly the unclaimed amount, and its total stayed equal to claimed plus unclaimed.

## Limits

Not checked on spot markets; spot fills write no fill record, so there only the app's totals can show the fee. When one match closes a position and opens the other side, the network writes it as two fill records and shows the app fee for the whole match on one of them; the totals still add up. Not yet run on mainnet.

Also on the docs: https://docs.vordium.com/security/ai-audit/#builder-fees
