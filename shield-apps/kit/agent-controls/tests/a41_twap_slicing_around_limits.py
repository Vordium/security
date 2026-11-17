"""A41 - TWAP slicing around the agent's limits. Each slice is under the largest order, but the whole TWAP is ten times
the largest position; and a TWAP at 10x under a 5x policy. A positive control first (a small TWAP inside every limit is
taken). Expected: both refused by the agent's limits."""
from shield import *

run = Run("A41", "agent TWAP whose slices hide a total above its limits")
net = Net(run)
# exposure cap far above every case, so only the largest position (case 1) or the leverage (case 2) can refuse
s = setup_or_end(run, net, policy=default_policy(now_ms() + 3600_000, max_total_exposure_6dec=10 ** 9 * E6))
eth, lot = s["eth"], int(s["eth"]["lot18dec"])
ctl = twap_body(net, s["agent_key"], s["owner"], eth)
r0 = post("/twap/place", ctl)
run.step("control", http=r0["http"], answer=r0["answer"])
if not (r0["http"] and r0["http"] < 300):
    run.end(CANNOT, "the control TWAP inside every limit was not taken")
res = {}
for label, kw in (("total_over_position", dict(total18=lot * 900 * 100, slices=100)),
                  ("leverage_10x", dict(leverage_bps=10 * 10000))):
    b = twap_body(net, s["agent_key"], s["owner"], eth, **kw)
    r = post("/twap/place", b)
    time.sleep(4)
    ev = next((e for e in agent_events(s["agent"], 20) if str(e.get("client_nonce")) == str(b["client_nonce"])), {})
    reason = (r["answer"] or {}).get("reason") if isinstance(r["answer"], dict) else None
    res[label] = {"http": r["http"], "reason": reason or ev.get("reason") or agent_reason(r["answer"]),
                  "running": bool(twap_running(s["owner"], b["client_nonce"]))}
    run.step(label, http=r["http"], answer=r["answer"], running=res[label]["running"])
if any(v["running"] or (v["http"] and v["http"] < 300) for v in res.values()):
    run.end(WORKS, "a TWAP above the agent's limits was taken: " + json.dumps(res))
want = {"total_over_position": ("max_position", "max_order"), "leverage_10x": ("max_leverage",)}
named = {k: v["reason"] in want[k] for k, v in res.items()}
if not all(v["reason"] for v in res.values()):
    run.end(CANNOT, "refused for another reason, so the agent's limits were not reached: " + json.dumps(res))
if not all(named.values()):
    run.step("attribution", note="the network refused with agent_refused but named no reason; the exposure cap is set out of reach, "
             "so the refusal comes from the position or leverage limit", named=named)
r = submit(signed_op(s["owner_key"], "RevokeAgent", {"owner": s["owner"], "agent": s["agent"], "nonce": NONCE()}))
run.step("cleanup_revoke", http=r["http"])
run.end(HOLDS, "both refused by the agent's limits (exposure out of reach): " + json.dumps(res))
