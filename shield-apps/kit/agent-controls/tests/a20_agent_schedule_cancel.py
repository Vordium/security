"""A20 - an agent signs ScheduleCancel (the dead-man switch) for its owner: arming it at once would cancel every order
of the account and refuse the account's new orders; clearing it would remove the owner's safety. Expected: refused;
the switch state does not change."""
from shield import *
from vordium import schedule_cancel as SC

run = Run("A20", "agent arms or clears its owner's dead-man switch")
net = Net(run)
s = setup_or_end(run, net)
owner = s["owner"]
read = lambda: get(f"/schedule-cancel/{owner}")
before = read()
run.step("state_before", state=before)
if isinstance(before, dict) and before.get("active") is False:
    run.end(CANNOT, "the dead-man switch is not active on this network")
sep = separator("VordCore")
moved = []
for label, t in (("arm_ahead", now_ms() + 30_000), ("clear", 0)):
    before = read()
    n = NONCE()
    sig = SC.sign_schedule_cancel(s["agent_key"], owner, t, n, domain_separator=sep)
    r = post("/schedule-cancel", SC.schedule_cancel_body(owner, t, n, sig))
    run.step("sent_" + label, http=r["http"], answer=r["answer"])
    if not unchanged(run, "switch_" + label, read, before, 10):
        moved.append(label)
if moved:
    run.end(WORKS, "an agent's signature changed the owner's dead-man switch: " + ", ".join(moved))
run.end(HOLDS, "the owner's dead-man switch did not change after either signature")
