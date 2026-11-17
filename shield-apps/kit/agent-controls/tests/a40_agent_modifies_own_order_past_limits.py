"""A40 - an agent places an allowed small order, then modifies its OWN order past its limits: ten times its largest
order, a price outside its oracle band. Funded owner. Expected: each change refused; the order stays as placed."""
from shield import *
from vordium import mm

run = Run("A40", "agent modifies its own order past its limits", extra=funded_args)
net = Net(run)
s = funded_setup(run, net, TPSL_CAPS, key_attr="agent2_key_file", name="shield tpsl check")
eth = s["eth"]
p8 = net.px(eth, "0.94")
b = order_body(s["agent_key"], s["owner"], eth["pairId"], 0, net.size18(eth, "15", p8), p8)
f = order_fate(s["owner"], s["agent"], b["clientNonce"], post("/order/place", b), 12)
run.step("agent_order", fate={k: v for k, v in f.items() if k != "order"})
if not f["outcome"].startswith("accepted") or f.get("order_id") is None:
    owner_cancel_all_resting(run, s["owner_key"])
    run.end(CANNOT, "the agent's own order did not rest")
oid = int(f["order_id"])
snap = lambda: [{k: o.get(k) for k in ("price_8dec", "size", "remaining_18dec", "pair_id")} for o in orders_of(s["owner"]) if str(o.get("client_nonce")) in SENT_NONCES]
before = snap()
lot = int(eth["lot18dec"])
changed = []
for label, np8, ns in (("ten_times_largest", p8, lot * 1000 * 10), ("outside_band", net.px(eth, "0.5"), lot * 100)):
    n = now_ms()
    SENT_NONCES.add(str(n))
    sig = mm.sign(s["agent_key"], mm.digest(mm.modify_v2_struct_hash(s["owner"], oid, np8, ns, n), separator("VordCore")))
    r = post("/order/modify", mm.modify_body(s["owner"], oid, np8, ns, n, sig))
    time.sleep(6)
    after = snap()
    run.step("modify_" + label, http=r["http"], answer=r["answer"], orders=after)
    if after != before:
        changed.append(label)
        before = after
owner_cancel_all_resting(run, s["owner_key"])
if changed:
    run.end(WORKS, "the agent's own order was changed past its limits: " + ", ".join(changed))
run.end(HOLDS, "both changes refused; the order stayed as placed")
