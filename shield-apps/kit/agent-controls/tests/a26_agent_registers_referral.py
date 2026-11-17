"""A26 - an agent (or any stranger) registers the owner as a referred trader under the attacker's referrer, so the
attacker earns a share of the owner's fees. The signed message names no trader; the body does. Expected: refused (the
signer must be the trader)."""
from shield import *
from vordium.referral import register_trader_message, sign_referral_message

run = Run("A26", "agent registers its owner under a referrer")
net = Net(run)
code = None
tiers = get("/referral/tiers")
lb = requests.get("https://testnet.vordex.xyz/ranks?window=all&sort=volume&kind=all&limit=50", headers=UA, timeout=15)
cands = []
try:
    cands = [row.get("account") for row in (lb.json().get("rows") or lb.json().get("ranks") or []) if isinstance(row, dict)]
except Exception:
    pass
referrer = None
for a in cands:
    st = get(f"/referral/stats/{a}") if a else None
    if isinstance(st, dict) and st.get("code"):
        referrer, code = a.lower(), st["code"]
        break
run.step("referrer", referrer=referrer, code=code)
if not code:
    run.end(CANNOT, "no referral code could be found on the test network to register under")
s = setup_or_end(run, net)
owner = s["owner"]
before = get(f"/referral/stats/{owner}")
n = now_ms()
msg = register_trader_message(TESTNET_CHAIN_ID, referrer, code, n, net.phase)
sig = sign_referral_message(s["agent_key"], msg)
r = post("/referral/register", {"trader": owner, "referrer": referrer, "code": code, "nonce": n, "signature": sig})
run.step("sent", http=r["http"], answer=r["answer"])
strip = lambda j: {k: v for k, v in (j or {}).items() if "refer" in k.lower()} if isinstance(j, dict) else j
if unchanged(run, "referral", lambda: strip(get(f"/referral/stats/{owner}")), strip(before), 10):
    run.end(HOLDS, f"the owner was not registered under the referrer (intake {r['http']})")
run.end(WORKS, "an agent's signature registered its owner under a referrer")
