"""A21 - an agent signs SetMarginMode for its owner (switching a market between cross and isolated changes how the
owner's positions are liquidated). Expected: refused; the mode does not change."""
from shield import *
from vordium.account_ops import SET_MARGIN_MODE, margin_mode_body
import json

run = Run("A21", "agent changes its owner's margin mode")
net = Net(run)
s = setup_or_end(run, net)
owner, eth = s["owner"], s["eth"]
read = lambda: get(f"/account/cross/{owner}")
before = read()
run.step("before", state=before)
cur = None
if isinstance(before, dict):
    cur = next((m.get("mode") for m in before.get("modes") or [] if str(m.get("pair_id")) == str(eth["pairId"])), before.get("default_mode"))
want = 2 if cur in (1, "cross") else 1
n = NONCE()
sig = typed_sign(s["agent_key"], "VordCore", "SetMarginMode", SET_MARGIN_MODE,
                 {"owner": owner, "pairId": eth["pairId"], "mode": want, "nonce": n})
r = post("/margin/mode", json.loads(margin_mode_body(owner, eth["pairId"], want, n, sig)))
run.step("sent", http=r["http"], answer=r["answer"], asked_mode=want)
if unchanged(run, "margin", read, before, 12):
    run.end(HOLDS, f"the margin mode did not change (intake {r['http']})")
run.end(WORKS, "an agent's signature changed the owner's margin mode")
