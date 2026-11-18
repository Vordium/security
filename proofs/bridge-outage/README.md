# A data-provider outage holds bridge deposits and payouts, then settles each exactly once

**BUILT, NOT PROVEN**

## Network

Testnet (vault on Arbitrum Sepolia, test token with no value)

## Code version

The testnet network on the run date

## Check it yourself

Every result below is in public records. On the testnet read service (https://testnet.vordex.xyz/chain):

- `GET /bridge/v4/deposit/tx/{transaction}?chain_id=421614` for the two deposits
  (0xdc94fb55d1aef92e7b37a99be67c5de6cb51c253b54471e0174949c3492ef8bc, 0xf9363a7957aa654c47ca2f23a6ec387048a2ce4e4da55e956cc656100e9cb16a);
- `GET /bridge/v4/withdrawal/0x3888bA40B512E74440403caC927c79061Aa2e076/{26|27}` for the two withdrawals;
- `GET /events/account/0x3888bA40B512E74440403caC927c79061Aa2e076` for the account's records (one `deposit_credited` per
  deposit, one `withdrawal_requested` per withdrawal);
- on Arbitrum Sepolia, the receipts of the two payout transactions
  (0x21a0b013a0346d88e464650129b8cdc62115ce14882d8d759112b9a1179aeb66, 0xcd3769825085a7e71ba6c5c7801be2d0fde75f5d91baad3083935fa86ab183de):
  each holds one transfer of 4 test USDC to the account.

## Last run (UTC date)

18 Nov 2026

## Result

Every validator reads the vault chain through two separately keyed endpoints that must agree on the same block hash and the
same values; a deposit is credited only from a quorum of validators with such a reading, and a payout is signed only from
one. On all 7 test validators one endpoint was made unreachable on the operator's side, then both, for 18 minutes each, with
a deposit (7 test USDC) and a withdrawal (5 test USDC: 4 paid out plus a 1 USDC fee) sent in each stage.

While either endpoint was unreachable, no validator made an agreed reading (none fell back to the remaining endpoint), the
public coverage answer said `unavailable`, and the deposits stayed pending: not credited, not refused, not dropped. The
withdrawals were accepted at once (the amount left the account's balance) and stayed pending; no validator signed a payout
and the vault paid nothing.

When the endpoints were restored, the first five validators back (a quorum of 5 of 7) credited both deposits (testnet heights
306,576,599 and 306,578,436) and signed both payouts, paid on Arbitrum Sepolia in blocks 330,464,069 and 330,464,156, about
5 minutes after the restore began. From public records: one credit record per deposit, one withdrawal record per withdrawal,
one 4 test USDC transfer per payout; the account's Arbitrum Sepolia balance rose by exactly 8 and its network balance by
exactly 14 − 10; the vault's deposit total rose by exactly 14, its paid total by exactly 8. Nothing was credited or paid twice
and nothing was lost.

## Limits

The outage was a refused connection. A provider that answers with wrong data is a different case (two endpoints that disagree
produce no reading) and was not run here. Each stage lasted 18 minutes; a withdrawal carries a deadline (2 hours in this run),
and an outage longer than that deadline ends in a refund to the account instead of a payout — that path was not run here.
One run on the testnet; not run on mainnet.
