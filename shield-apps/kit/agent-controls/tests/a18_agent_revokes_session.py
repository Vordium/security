"""A18 - the owner has an app session; its agent signs SessionRevoke for the owner (to cut the owner's own trading
key). Expected: the session stays."""
from shield import *
from vordium.account_ops import AccountOps, SESSION_REVOKE, session_revoke_body
import json

run = Run("A18", "agent revokes its owner's app session")
net = Net(run)
s = setup_or_end(run, net)
sk = new_key(run, "session")
owner = s["owner"]
res = AccountOps(s["owner_key"]).create_session(addr(sk), now_ms() + 3600_000, wait_s=40)
run.step("owner_session", applied=res.applied, status=res.status_code)
if res.applied is not True:
    run.end(CANNOT, "the owner's session could not be created")
n = NONCE()
sig = typed_sign(s["agent_key"], "VordexSession", "SessionRevoke", SESSION_REVOKE, {"owner": owner, "nonce": n})
r = post("/session/revoke", json.loads(session_revoke_body(owner, addr(sk), n, sig)))
run.step("sent", http=r["http"], answer=r["answer"])
read = lambda: (get(f"/session/get?owner={owner}") or {}).get("session_key")
if unchanged(run, "session", read, read(), 12) and read():
    run.end(HOLDS, "the owner's session stayed")
run.end(WORKS, "an agent's signature ended the owner's app session")
