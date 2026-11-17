# SHIELD E — agent controls (test network)

**Scope.** What an AI agent's key can and cannot do to the account that registered it: the owner's policy limits (markets,
largest order, exposure, leverage, daily loss, active hours, capabilities, reduce-only, price band), who may change them,
what an agent key may sign (sessions, money moves, withdrawals, builder fees, margin mode, dead-man switch, other agents),
nonces and replays, signed batches, stop orders and TWAP orders, and the owner's orders and the app session's orders.
**Audited.** The test network release `420107b0e05afff2`, as named by the network's own release record
(`https://rpc-testnet.vordium.com/truth/v1/record`, signed index current, read 2026-11-17); signed with the published Python
SDK `vordium` 1.6.0 (commit dce6d79).
**Kit.** `kit/agent-controls/` (sha256 in SHA256SUMS).
**Run:** 2026-11-17, fresh throwaway test-network accounts.

**Vectors: 61** — covered 46 (1 by reading the published rule; 2 by an earlier published proof) · by design 2 · open 13.

| Check | What it checks | Result |
|---|---|---|
| `a01_market_not_allowed` | the agent orders on a market its policy does not allow | PASS |
| `a02_above_max_order` | the agent orders twice its largest order | PASS |
| `a03_leverage_above_policy` | the agent orders at 10x under a 5x policy | PASS |
| `a04_exposure_above_cap` | the agent orders past its total exposure cap | PASS |
| `a05_policy_disabled` | the agent orders while the owner has disabled its policy | PASS |
| `a06_outside_active_hours` | the agent orders outside its active hours | PASS |
| `a07_capability_not_granted` | the agent places an order with no place capability | PASS |
| `a08_reduce_only_mode` | the agent opens a position under a reduce-only policy | PASS |
| `a09_price_band` | the agent prices far outside its oracle band | PASS |
| `a10_agent_loosens_own_policy` | the agent signs a looser policy for itself, field by field (exposure, leverage 0 = unlimited, fee cap 0 = unlimited, daily loss, expiry, band, lock auto-clear, side mode, capabilities, operations limit, active hours, re-enabling) | PASS |
| `a11_agent_nonce_poison` | the agent signs its own operation with the highest nonce it can, to stop the owner from revoking it | PASS |
| `a12_agent_sets_market_limit` | the agent allows itself a new market and a huge order size | PASS |
| `a13_agent_registers_agent` | the agent registers another agent for its owner | PASS |
| `a14_agent_acts_on_sibling` | the agent revokes or disables another agent of the same owner | PASS |
| `a15_agent_renames_itself` | the agent renames itself ("Owner wallet") | PASS |
| `a16_agent_clears_lock` | the agent clears its own reduce-only lock | PASS |
| `a17_agent_creates_session` | the agent creates an app session for its owner | PASS |
| `a18_agent_revokes_session` | the agent ends its owner's app session | PASS |
| `a19_agent_stop_all_signers` | the agent signs "stop all signers" for its owner | PASS |
| `a20_agent_schedule_cancel` | the agent arms or clears its owner's dead-man switch | PASS |
| `a21_agent_margin_mode` | the agent switches its owner's margin mode | PASS |
| `a22_agent_sets_mmp` | the agent sets its owner's market maker protection | PASS |
| `a23_agent_approves_builder` | the agent approves a builder fee to an address it controls | PASS |
| `a24_agent_bridge_withdraw` | the agent withdraws its owner's USDC through the bridge to its own address | PASS |
| `a25_agent_money_ops` | the agent signs the owner's pool and staking money operations | PASS |
| `a26_agent_registers_referral` | the agent registers its owner under a referrer | PASS |
| `a27_agent_signs_for_other_owner` | the agent orders for an account that never registered it | PASS |
| `a28_agent_cancels_owner_order` | the agent cancels an order its owner placed | not run in this record (needs a funded test account) |
| `a29_agent_cancel_all_scope` | the agent sends cancel-all for its owner | not run in this record (needs a funded test account) |
| `a30_agent_modifies_owner_order` | the agent moves an order its owner placed | not run in this record (needs a funded test account) |
| `a31_batch_hides_agent_order` | the agent hides a forbidden-market order and an oversized order inside a signed batch | not run in this record (needs a funded test account) |
| `a32_agent_order_replay` | the same signed agent order is sent twice, and again after cancel | not run in this record (needs a funded test account) |
| `a33_far_future_nonce` | the agent signs with a nonce 30 days ahead | not run in this record (needs a funded test account) |
| `a34_cross_network_agent_order` | an agent order signed for the main network is sent to the test network | PASS |
| `a35_twap_by_agent` | after a positive control (a TWAP on the allowed market is taken), the agent starts a TWAP on a forbidden market, and another after the owner revoked it | PASS |
| `a40_agent_modifies_own_order_past_limits` | the agent modifies its own order to ten times its largest order, and outside its band | not run in this record (needs a funded test account) |
| `a41_twap_slicing_around_limits` | after a positive control, a TWAP whose slices are each under the largest order but whose total is far above, and one at 10x under a 5x policy | PASS |
| `a42_agent_stop_orders` | after a positive control (a small stop rests), a stop on a forbidden market and one above the largest order | PASS |
| `a43_builder_fee_in_agent_order` | the owner approves builder X at a small fee; the agent's orders name another builder, or X at 100 times the fee | PASS |
| `a45_agent_cancels_session_order` | the app session places a stop; the agent cancels it, then sends cancel-all | PASS |
| `a47_active_hours_wrap` | active hours that wrap past midnight: one window containing now, one leaving it out | PASS |
| `a48_dead_man_switch_fires` | the app session arms the dead-man switch and never refreshes it | PASS |

Checks marked "not run" need a funded test-network account; they are in the kit and were not part of this record.

**Open:**
- A-POL-10: under work.
- A-POL-13: under work.
- A-POL-14: under work.
- A-OWN-08: under work.
- A-MON-04: under work.
- A-MON-05: under work.
- A-SIG-05: under work.
- A-SIG-06: under work.
- A-SIG-07: under work.
- A-SCOPE-04: under work.
- A-SCOPE-07: under work.
- A-TWAP-02: under work.
- A-TWAP-04: under work.
- lifecycle (revoke, expiry, stop all): under work.

**Re-run:** `cd kit/agent-controls && PYTHON=venv/bin/python ./run-all.sh` (after `pip install "vordium==1.6.0" eth-account requests`;
the funded checks add `--owner-key-file PATH`).
