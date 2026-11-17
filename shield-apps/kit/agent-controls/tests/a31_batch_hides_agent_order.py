"""A31 - an agent wraps orders its policy forbids inside a signed batch (/order/batch-signed): one on a market that is
not allowed (BTC) and one above its largest ETH order, both resting away from the book. A batch is judged as one
operation; the agent's limits must still apply to every order in it. Expected: neither order rests."""
from shield import *
from vordium import mm

run = Run("A31", "agent hides forbidden orders inside a batch", extra=funded_args)
net = Net(run)
s = funded_setup(run, net)
eth, btc = s["eth"], net.pair("BTC")
before = set(resting_ids(s["owner"]))
pb, pe = net.px(btc, "0.95"), net.px(eth, "0.95")
n0 = now_ms()
SENT_NONCES.update({str(n0 + 1), str(n0 + 2)})
acts = [mm.place(btc["pairId"], "buy", net.size18(btc, "15", pb), pb, n0 + 1),
        mm.place(eth["pairId"], "buy", int(eth["lot18dec"]) * 1000 * 3, pe, n0 + 2)]
n = NONCE()
sig = mm.sign(s["agent_key"], mm.digest(mm.batch_struct_hash(s["owner"], n, acts), separator("VordCore")))
r = post("/order/batch-signed", mm.batch_body(s["owner"], n, acts, sig))
run.step("attack", http=r["http"], answer=r["answer"])
time.sleep(8)
new = [o for o in orders_of(s["owner"]) if str(o.get("client_nonce")) in (str(n0 + 1), str(n0 + 2))]
run.step("after", new_orders=new, agent_refusals=[e for e in agent_events(s["agent"], 10) if e.get("kind") == "agent_refused"][:4])
owner_cancel_all_resting(run, s["owner_key"])
if new:
    run.end(WORKS, f"{len(new)} order(s) the agent's policy forbids rest after a batch")
if r["http"] is None or (r["http"] >= 500):
    run.end(CANNOT, "the batch route did not answer")
run.end(HOLDS, f"no forbidden order rests (intake {r['http']})")
