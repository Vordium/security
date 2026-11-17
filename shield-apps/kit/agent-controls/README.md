# Agent controls: attack checks (Vordium test network)

These checks attack the controls an account owner puts on an AI agent: the policy limits, the allowed markets, who may
change them, what an agent key may sign, nonces, batches and TWAP orders. Each check sends real signed requests to the
Vordium test network and judges the result from the network's own answers and reads.

**Test network only.** Every check refuses any network other than the Vordium test network (chain id 101102) before
anything is signed. Test network tokens have no value.

## What you need

- Python 3.10 or later
- the public packages: `pip install "vordium==1.6.0" eth-account requests`
- for the checks marked *funded*: a test-network owner key with at least 30 test USDC. Claim test USDC at
  <https://testnet.vordex.xyz/faucet> to the owner's address (trading account).

Every other check makes its own throwaway owner and agent keys. Keys are written mode 600 into a folder of mode 700
(`--keys-dir`, default `./keys`) and are never printed: only addresses appear in the output.

## Run

```bash
python3 -m venv venv
venv/bin/pip install "vordium==1.6.0" eth-account requests
PYTHON=venv/bin/python ./run-all.sh                                   # every check that needs no funds
PYTHON=venv/bin/python SHIELD_AGENT_KEY_FILE=keys/funded-agent.key \
  ./run-all.sh --owner-key-file /path/to/owner.key a24_agent_bridge_withdraw.py a28_agent_cancels_owner_order.py \
  a29_agent_cancel_all_scope.py a30_agent_modifies_owner_order.py a31_batch_hides_agent_order.py \
  a32_agent_order_replay.py a33_far_future_nonce.py                   # the funded checks
PYTHON=venv/bin/python SHIELD_AGENT2_KEY_FILE=keys/funded-agent2.key \
  ./run-all.sh --owner-key-file /path/to/owner.key \
  a40_agent_modifies_own_order_past_limits.py # a second agent with the modify and stop capabilities
```

One check alone: `cd tests && ../venv/bin/python a01_market_not_allowed.py --keys-dir ../keys`.
The funded checks share one agent of the funded owner (`--agent-key-file`, made and registered on first use, live for
30 minutes), because an account has only a few agent places. Their clean-up cancels only the orders the check itself
placed. The position checks use the funded account's ETH position when it has one (its size is never changed; its
take-profit / stop-loss is put back afterwards), else they open a small one and close it.

Each run writes `results/run-N/` with one JSON record and one log per check, and `summary.txt`.

**Exit codes: 0 = the defence holds, 1 = the attack works, 3 = the check cannot run** (and says why).

## The checks

| Check | Attack | Defence expected |
|---|---|---|
| `a01_market_not_allowed` | the agent orders on a market its policy does not allow | refused: `market_not_allowed` |
| `a02_above_max_order` | the agent orders twice its largest order | refused: `max_order` |
| `a03_leverage_above_policy` | the agent orders at 10x under a 5x policy | refused: `max_leverage` |
| `a04_exposure_above_cap` | the agent orders past its total exposure cap | refused: `max_total_exposure` |
| `a05_policy_disabled` | the agent orders while the owner has disabled its policy | refused: `policy_disabled` |
| `a06_outside_active_hours` | the agent orders outside its active hours | refused: `outside_active_window` |
| `a07_capability_not_granted` | the agent places an order with no place capability | refused: `capability_not_granted` |
| `a08_reduce_only_mode` | the agent opens a position under a reduce-only policy | refused: `reduce_only_or_side` |
| `a09_price_band` | the agent prices far outside its oracle band | refused: `price_outside_band` |
| `a10_agent_loosens_own_policy` | the agent signs a looser policy for itself, field by field (exposure, leverage 0 = unlimited, fee cap 0 = unlimited, daily loss, expiry, band, lock auto-clear, side mode, capabilities, operations limit, active hours, re-enabling) | an agent's own tightening applies; no loosening does |
| `a11_agent_nonce_poison` | the agent signs its own operation with the highest nonce it can, to stop the owner from revoking it | the owner's policy change and revoke still apply |
| `a12_agent_sets_market_limit` | the agent allows itself a new market and a huge order size | stored limits unchanged |
| `a13_agent_registers_agent` | the agent registers another agent for its owner | no new agent |
| `a14_agent_acts_on_sibling` | the agent revokes or disables another agent of the same owner | the other agent stays live, its policy unchanged |
| `a15_agent_renames_itself` | the agent renames itself ("Owner wallet") | name unchanged |
| `a16_agent_clears_lock` | the agent clears its own reduce-only lock | refused |
| `a17_agent_creates_session` | the agent creates an app session for its owner | no session |
| `a18_agent_revokes_session` | the agent ends its owner's app session | session stays |
| `a19_agent_stop_all_signers` | the agent signs "stop all signers" for its owner | nothing stopped |
| `a20_agent_schedule_cancel` | the agent arms or clears its owner's dead-man switch | switch unchanged |
| `a21_agent_margin_mode` | the agent switches its owner's margin mode | mode unchanged |
| `a22_agent_sets_mmp` | the agent sets its owner's market maker protection | unchanged |
| `a23_agent_approves_builder` | the agent approves a builder fee to an address it controls | no approval |
| `a24_agent_bridge_withdraw` *(funded for a definitive result)* | the agent withdraws its owner's USDC through the bridge to its own address | refused; no withdrawal exists |
| `a25_agent_money_ops` | the agent signs the owner's pool and staking money operations | each refused for its signer |
| `a26_agent_registers_referral` | the agent registers its owner under a referrer | not registered |
| `a27_agent_signs_for_other_owner` | the agent orders for an account that never registered it | refused |
| `a28_agent_cancels_owner_order` *(funded)* | the agent cancels an order its owner placed | refused: `not_agents_order` |
| `a29_agent_cancel_all_scope` *(funded)* | the agent sends cancel-all for its owner | the owner's order survives |
| `a30_agent_modifies_owner_order` *(funded)* | the agent moves an order its owner placed | refused: `not_agents_order` |
| `a31_batch_hides_agent_order` *(funded)* | the agent hides a forbidden-market order and an oversized order inside a signed batch | each order in the batch refused by the agent's limits |
| `a32_agent_order_replay` *(funded)* | the same signed agent order is sent twice, and again after cancel | one order at most |
| `a33_far_future_nonce` *(funded)* | the agent signs with a nonce 30 days ahead | refused; normal orders still go through |
| `a34_cross_network_agent_order` | an agent order signed for the main network is sent to the test network | refused (`--send-to-mainnet` also sends one test-network signature to the main network, which must refuse it) |
| `a35_twap_by_agent` | after a positive control (a TWAP on the allowed market is taken), the agent starts a TWAP on a forbidden market, and another after the owner revoked it | both refused; none running |
| `a40_agent_modifies_own_order_past_limits` *(funded)* | the agent modifies its own order to ten times its largest order, and outside its band | both refused |
| `a41_twap_slicing_around_limits` | after a positive control, a TWAP whose slices are each under the largest order but whose total is far above, and one at 10x under a 5x policy | both refused by the agent's limits |
| `a42_agent_stop_orders` | after a positive control (a small stop rests), a stop on a forbidden market and one above the largest order | both refused when placed |
| `a43_builder_fee_in_agent_order` | the owner approves builder X at a small fee; the agent's orders name another builder, or X at 100 times the fee | both refused |
| `a45_agent_cancels_session_order` | the app session places a stop; the agent cancels it, then sends cancel-all | the session's order survives |
| `a47_active_hours_wrap` | active hours that wrap past midnight: one window containing now, one leaving it out | rests inside; refused outside (`outside_active_window`) |
| `a48_dead_man_switch_fires` | the app session arms the dead-man switch and never refreshes it | at the deadline the stop is cancelled and new orders are refused |

What happens to an agent's resting orders and TWAPs at a revoke, at a policy or registration expiry, and when the owner
stops every signer at once is judged by the revoke and expiry lifecycle checks, which follow each order to its end.

## Reading a result

Each record in `results/run-N/<check>.json` holds every request's answer as the network gave it (refusal codes
verbatim), the reads before and after, and the verdict. The network publishes the meaning of each refusal code in its
spec: <https://testnet.vordex.xyz/network-spec.json> under `agents.refusalCodes` and `orders.refusalCodes`.
