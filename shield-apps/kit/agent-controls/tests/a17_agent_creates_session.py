"""A17 - an agent signs SessionCreate for its owner, naming a fresh key as the owner's app session (a session signs
like the owner, with no agent policy). Expected: refused; the owner has no session afterwards."""
from shield import *
from vordium.account_ops import SESSION_CREATE, session_create_body
import json

run = Run("A17", "agent creates an app session for its owner")
net = Net(run)
s = setup_or_end(run, net)
sk = new_key(run, "session")
owner = s["owner"]
exp_s = now_ms() // 1000 + 3600
val = {"sessionKey": addr(sk), "expiresAt": exp_s, "nonce": NONCE()}
sig = typed_sign(s["agent_key"], "VordexSession", "SessionCreate", SESSION_CREATE, val)
r = post("/session/create", json.loads(session_create_body(owner, addr(sk), exp_s, val["nonce"], sig)))
run.step("sent", http=r["http"], answer=r["answer"])
read = lambda: (lambda j: (j or {}).get("session_key") if isinstance(j, dict) else None)(get(f"/session/get?owner={owner}"))
time.sleep(6)
held = read()
run.step("session_after", session_key=held)
if held and str(held).lower() == addr(sk).lower():
    run.end(WORKS, "the chain gave the owner an app session on an agent's signature")
run.end(HOLDS, f"no session was created (intake {r['http']})")
