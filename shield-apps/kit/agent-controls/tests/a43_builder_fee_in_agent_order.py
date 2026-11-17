"""A43 - a builder fee inside an agent's order. The owner approves builder X at 1 (tenth of a basis point); the agent then
signs orders naming (a) a builder the owner never approved (the agent's own address) and (b) builder X at 100 times the
approved fee. Expected: both refused; a builder fee is never paid past what the owner approved."""
from shield import *
from vordium import builder as B

run = Run("A43", "agent order naming a builder fee the owner did not approve")
net = Net(run)
s = setup_or_end(run, net)
owner, eth = s["owner"], s["eth"]
x = addr(new_key(run, "builder"))
appr = get(f"/builder/approvals/{owner}") or {}
if appr.get("active") is not True:
    run.end(CANNOT, "builder fees are not active on this network")
sep = separator("VordCore")
sg = B.approve_builder_fee(s["owner_key"], owner, x, 1, int(appr.get("nonce") or 0) + 1, now_ms() // 1000 + 120, sep)
r = post(sg.route, sg.body)
ok = wait_until(lambda: any(str(a.get("builder", "")).lower() == x.lower() for a in (get(f"/builder/approvals/{owner}") or {}).get("approvals") or []), 20)
run.step("owner_approves", http=r["http"], answer=r["answer"], applied=bool(ok))
if not ok:
    run.end(CANNOT, "the owner's approval did not apply")
p8 = near(net, eth)
size = net.size18(eth, "20", p8)
res = {}
for label, bld, fee in (("unapproved_builder", s["agent"], 1), ("fee_above_approval", x, 100)):
    n = now_ms()
    SENT_NONCES.add(str(n))
    o = B.place_order_v3(s["agent_key"], owner, eth["pairId"], 0, size, p8, 10000, 1, n, now_ms() // 1000 + 120, bld, fee, sep)
    r = post(o.route, o.body)
    time.sleep(5)
    res[label] = {"http": r["http"], "code": (r["answer"] or {}).get("code") if isinstance(r["answer"], dict) else None,
                  "rests": bool(nonce_resting(owner, n))}
    run.step(label, http=r["http"], answer=r["answer"], rests=res[label]["rests"])
if any(v["rests"] or (v["http"] and v["http"] < 300) for v in res.values()):
    run.end(WORKS, "an agent order with a builder fee the owner did not approve was taken: " + json.dumps(res))
run.end(HOLDS, "both refused at intake: " + json.dumps(res))
