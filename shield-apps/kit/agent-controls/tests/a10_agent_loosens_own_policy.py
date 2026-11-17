"""A10 - an agent signs SetAgentPolicyV1 for itself to LOOSEN its limits (the chain lets an agent only tighten).
A positive control first: the agent tightens one field and the chain applies it (so the agent-signed path is live).
Then one loosening per field, each checked against the stored policy: higher exposure, leverage 0 (= unlimited),
higher leverage, fee cap 0 (= unlimited), higher daily loss, later expiry, wider band, automatic lock clearing,
open-and-reduce from reduce-only, a new capability, operations limit off, active hours off, and finally re-enabling a
policy the owner disabled. Expected: the control applies; no loosening ever does."""
import dataclasses
from shield import *
from vordium.agent_ops import set_policy
from vordium.policy import policy_value

run = Run("A10", "agent loosens its own policy")
net = Net(run)
exp = now_ms() + 3600_000
base = default_policy(exp, side_mode=1, max_leverage_bps=5 * 10000, daily_fee_cap_6dec=10 * E6, oracle_band_bps=500,
                      ops_per_window=100, ops_window_ms=60_000, active_from_ms_of_day=1, active_to_ms_of_day=86_399_999)
s = setup_or_end(run, net, policy=base)
owner, agent, ak = s["owner"], s["agent"], s["agent_key"]
VOLATILE = ("set_ms", "set_by_agent")


def stored():
    p = dict(policy_of(agent_rec(owner, agent)))
    return {k: v for k, v in p.items() if k not in VOLATILE}


def agent_signs(pol, label):
    body = signed_op(ak, "SetAgentPolicyV1", policy_value(owner, agent, pol, NONCE()))
    r = submit(body)
    run.step("sent_" + label, http=r["http"], answer=r["answer"])
    return r


# control: a tightening the chain must apply
cur = dataclasses.replace(base, max_total_exposure_6dec=150 * E6)
before = stored()
agent_signs(cur, "control_tighten")
ok = wait_until(lambda: int(stored().get("max_total_exposure_6dec") or 0) == 150 * E6, 20)
rec = policy_of(agent_rec(owner, agent))
run.step("control", applied=bool(ok), set_by_agent=rec.get("set_by_agent"))
if not ok:
    run.end(CANNOT, "the agent's own tightening did not apply, so the agent-signed path could not be shown live")

tries = [
    ("exposure_up", dict(max_total_exposure_6dec=1000 * E6)),
    ("leverage_unlimited_0", dict(max_leverage_bps=0)),
    ("leverage_up", dict(max_leverage_bps=20 * 10000)),
    ("fee_cap_unlimited_0", dict(daily_fee_cap_6dec=0)),
    ("daily_loss_up", dict(daily_loss_limit_6dec=500 * E6)),
    ("expiry_later", dict(expires_ms=exp + 3600_000)),
    ("band_wider", dict(oracle_band_bps=1000)),
    ("lock_auto_clear_on", dict(lock_auto_clear=True)),
    ("side_open", dict(side_mode=0)),
    ("caps_all", dict(caps_bitmask=0b111111)),
    ("ops_limit_off", dict(ops_per_window=0, ops_window_ms=0)),
    ("active_hours_off", dict(active_from_ms_of_day=0, active_to_ms_of_day=0)),
]
loosened = []
for label, change in tries:
    before = stored()
    agent_signs(dataclasses.replace(cur, **change), label)
    if not unchanged(run, label, stored, before, 10):
        loosened.append(label)
        cur = dataclasses.replace(cur, **change)

# the owner disables the policy (a tightening, no cooldown); the agent turns it back on
from vordium.agent_ops import set_policy as _sp
off = dataclasses.replace(cur, enabled=False)
op, val = _sp(owner, agent, off, NONCE(), net.phase, now_ms())
r = submit(signed_op(s["owner_key"], op, val))
ok = wait_until(lambda: stored().get("enabled") is False, 20)
run.step("owner_disables", http=r["http"], applied=bool(ok))
if ok:
    before = stored()
    agent_signs(dataclasses.replace(off, enabled=True), "re_enable")
    if not unchanged(run, "re_enable", stored, before, 10):
        loosened.append("re_enable")
if loosened:
    run.end(WORKS, "the chain applied an agent-signed loosening: " + ", ".join(loosened))
run.end(HOLDS, f"the control tightening applied; none of {len(tries) + (1 if ok else 0)} agent-signed loosenings did")
