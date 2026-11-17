"""A24 - an agent signs a bridge withdrawal of its owner's USDC to an address it controls. Expected: refused (a
withdrawal is signed by the account's owner only); nothing leaves the account. With --owner-key-file (a funded owner)
the check is definitive: the owner has the money, so only the signer rule can stop it."""
from shield import *
from vordium import bridge_v4 as BV

run = Run("A24", "agent withdraws its owner's funds through the bridge")
net = Net(run)
if run.args.owner_key_file:
    ok_ = require_funded(run)
    ak = new_key(run, "agent")
    s = setup_agent(run, net, ok_, ak, "shield withdraw check", allowed_pair=net.pair("ETH"))
    s.update(owner_key=ok_, agent_key=ak)
else:
    s = setup_or_end(run, net)
owner = s["owner"]
thief = addr(new_key(run, "recipient"))
v = BV.fetch_vaults()
if not v.ok or not v.vaults:
    run.end(CANNOT, "the bridge vaults could not be read")
vault = v.vaults[0]
nxt, why = BV.fetch_next_nonce(owner)
chain_now = (get("/status") or {}).get("chain_time_ms") or now_ms()
intent = BV.WithdrawIntent(account=owner, vault_id=vault.id, recipient="0x" + "0" * 24 + thief[2:].lower(),
                           amount=max(v.withdrawal_fee + 1_000_000, 2_000_000), nonce=int(nxt or 0), route_kind=0,
                           destination_domain=vault.cctp_domain, max_fee=0, deadline=int(chain_now // 1000) + 600)
built, problem = BV.build_withdraw_intent(v, intent, int(nxt or 0), chain_now / 1000)
run.step("intent", vault=vault.id, nonce=nxt, amount_6dec=intent.amount, problem=problem)
if built is None:
    run.end(CANNOT, f"the withdrawal could not be built: {problem}")
bal_before = get(f"/balance/{owner}")
sig = BV.sign_withdraw_intent(s["agent_key"], built)
r = post("/bridge/v4/withdraw", BV.submit_body(built, sig))
run.step("sent", http=r["http"], answer=r["answer"])
time.sleep(8)
call = get(f"/bridge/v4/withdrawal/{owner}/{built.nonce}/call")
bal_after = get(f"/balance/{owner}")
run.step("after", withdrawal_call=call, balance_before=bal_before, balance_after=bal_after)
pending = isinstance(call, dict) and (call.get("found") is True or call.get("calldata") or call.get("data"))
if intake_refused(r) and not pending:
    code = r["answer"].get("code") if isinstance(r["answer"], dict) else None
    run.end(HOLDS, f"refused ({r['http']} {code}); no withdrawal exists")
if pending:
    run.end(WORKS, "a withdrawal signed by the agent exists for the owner's account")
run.end(CANNOT, "taken at intake with no withdrawal record yet; read again later")
