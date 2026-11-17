"""A25 - an agent signs the owner's pool and staking money operations (VlpWithdraw, Unstake, ClaimStakingRewards,
Stake, VlpDeposit) in the network's plain-text "Vordium Admin" format. Expected: each is refused because the signer is
not the owner (a refusal for the amount alone would not prove it: such a case is CANNOT RUN)."""
from shield import *
from vordium.money import MONEY_ROUTES, sign_money_op

SIGNER_WORDS = ("signature", "signer", "owner", "session", "recover", "not authorized", "unauthor", "forbidden")
run = Run("A25", "agent moves its owner's money through pool and staking operations")
net = Net(run)
s = setup_or_end(run, net)
owner = s["owner"].lower()
n = now_ms()
cases = {"VlpWithdraw": {"user": owner, "shares": 1, "nonce": n + 1}, "Unstake": {"owner": owner, "nonce": n + 2},
         "ClaimStakingRewards": {"owner": owner, "nonce": n + 3}, "Stake": {"owner": owner, "amount": 10 ** 18, "lock_ms": 0, "nonce": n + 4},
         "VlpDeposit": {"user": owner, "amount_6dec": 1_000_000, "nonce": n + 5}}
verdicts = {}
for op, args in cases.items():
    body = sign_money_op(s["agent_key"], op, args, TESTNET_CHAIN_ID, net.phase)
    r = post(MONEY_ROUTES[op], body)
    text = json.dumps(r["answer"]).lower()
    if not intake_refused(r):
        verdicts[op] = "taken"
    elif any(w in text for w in SIGNER_WORDS):
        verdicts[op] = "refused_signer"
    else:
        verdicts[op] = "refused_other"
    run.step("sent_" + op, http=r["http"], answer=r["answer"], verdict=verdicts[op])
time.sleep(6)
run.step("events_after", events=[e.get("kind") for e in account_events(owner, 20)])
if any(v == "taken" for v in verdicts.values()):
    run.end(WORKS, "the network took an agent-signed money operation: " + json.dumps(verdicts))
if all(v == "refused_signer" for v in verdicts.values()):
    run.end(HOLDS, "every agent-signed money operation was refused for its signer")
run.end(CANNOT, "some refusals do not name the signer: " + json.dumps(verdicts))
