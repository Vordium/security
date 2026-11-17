"""A16 - an agent signs ClearAgentLock for itself (to lift a daily-loss lock). On an account with no lock the check
reads the intake answer and the agent's lock state: an agent signature must be refused or change nothing. The full
form (a real lock) is the daily-loss step of the agent-control proof."""
from shield import *
from vordium.policy import clear_lock_value

run = Run("A16", "agent clears its own reduce-only lock")
net = Net(run)
s = setup_or_end(run, net)
owner, agent = s["owner"], s["agent"]
read = lambda: (rec_of(agent_rec(owner, agent)).get("risk_v1"), policy_of(agent_rec(owner, agent)).get("enabled"))
before = read()
r = submit(signed_op(s["agent_key"], "ClearAgentLock", clear_lock_value(owner, agent, now_ms() - 60_000, NONCE())))
run.step("sent", http=r["http"], answer=r["answer"])
same = unchanged(run, "lock_state", read, before, 10)
if intake_refused(r) and same:
    run.end(HOLDS, f"refused at intake ({r['http']} {r['answer'].get('code') or r['answer'].get('error')})")
if not same:
    run.end(WORKS, "the agent-signed clear changed the agent's state")
run.end(CANNOT, "taken at intake and nothing changed: with no lock to clear this says nothing more")
