"""C-30 (Python SDK, LIVE test network): the chain itself accepts the SDK's signatures, op by op.

The vectors in c09/c10 prove the two SDKs agree with each other and with what is published; this test asks the chain.
A fresh throwaway account (never funded; keys only in memory, never printed or written) signs with the SDK's normal API:
  SessionCreate (owner, VordexSession domain)  -> the chain must apply it (the session reads back confirmed);
  PlaceOrder (session key, VordCore)            -> the chain must judge the order, not the signature (an unfunded
                                                   account is refused for its balance, never for its signature);
  CancelOrder (session key)                     -> judged on the order (none), not the signature;
  ScheduleCancel / stop-all (owner)             -> accepted, then cleared;
  SessionRevoke (owner)                         -> applied (the session is gone).
Negative controls: the SAME order and cancel signed under the MAIN network's domain are refused for their signature.
That shows the chain checks signatures before balances, so "refused for balance" really means "signature valid".

Run:  python3 this file   (pip install vordium; talks to the public test network only)
Exit: 0 = every signature accepted as the SDK made it, 1 = the chain refused an SDK signature, 3 = cannot run.
"""
import json
import os
import re
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kit import MAINNET_GENESIS, Results, clean_env  # noqa: E402

warnings.simplefilter("ignore")
clean_env()
try:
    import requests
    import vordium
    from eth_account import Account
    from eth_utils import keccak
    from vordium import network as N, domains, schedule_cancel as sc
    from vordium.account_ops import AccountOps
    from vordium.caps import place_order_struct_hash, cancel_order_struct_hash
    from vordium.dex import Vordex, BUY, LIMIT, place_order_body, cancel_order_body
except Exception as e:  # pragma: no cover
    print(f"cannot import vordium: {e}")
    sys.exit(3)

R = Results(f"C-30 live test network accepts the SDK's signatures, Python SDK vordium {vordium.__version__}")
SIG = re.compile(r"signature|bad_sig|recover|signer", re.I)
try:
    net = N.resolve_network(network="testnet", timeout=15)
    N.set_network(net)
    N.signing_pin(net)
except Exception as e:
    print(f"the test network cannot be reached or does not match its pin: {e}")
    sys.exit(3)
rest = N.api_base(net).rstrip("/")
owner, session = Account.create(), Account.create()
print(f"throwaway owner {owner.address[:10]}…  session {session.address[:10]}…  chain {net.chain_id}")


def sig_refused(code, ans):
    return isinstance(code, int) and code >= 400 and bool(SIG.search(json.dumps(ans)))


ops = AccountOps(owner.key.hex(), network=net)
r = ops.create_session(session.address, int(time.time() * 1000) + 20 * 60_000, wait_s=45)
R.check("C-30a SessionCreate applied (confirmed on the chain)", r.applied is True, f"{r.status_code} {str(r.answer)[:120]}")
if r.applied is not True:
    R.finish()

vx = Vordex(network="testnet")
try:
    mark = float(vx.mark_price(1))
except Exception:
    mark = 0.0
price = round(mark * 0.97, 2) if mark > 0 else 1000.0
res = vx.place_order(session_key=session.key.hex(), owner=owner.address, pair_id=1, side=BUY, size="0.01",
                     price=str(price), order_type=LIMIT, retries=1)
code = res.get("status_code")
print(f"  order answer: {code} {json.dumps({k: res.get(k) for k in ('code', 'error', 'reason', 'status')})[:200]}")
R.check("C-30b PlaceOrder: judged on the account, not on the signature", not sig_refused(code, res), f"HTTP {code}")

# negative control: the same order signed under the MAIN network's domain
nonce = int(time.time() * 1000) + 7
p8, s18 = int(round(price * 1e8)) // 100 * 100, 10 ** 16
sh = place_order_struct_hash(owner.address, 1, 0, s18, p8, 10_000, 1, False, nonce, False, 0, 0)
d = keccak(b"\x19\x01" + domains.separator("VordCore", 101101, MAINNET_GENESIS) + sh)
sig = "0x" + Account._sign_hash(d, session.key).signature.hex().removeprefix("0x")[:128] if hasattr(Account, "_sign_hash") \
    else "0x" + Account.unsafe_sign_hash(d, session.key).signature.hex().removeprefix("0x")[:128]
body = place_order_body(owner.address, session.address, 1, 0, s18, p8, 10_000, 1, False, False, 0, 0, nonce, sig)
rr = requests.post(rest + "/order/place", json=body, timeout=15)
ans = rr.json() if rr.content else {}
print(f"  control answer: {rr.status_code} {json.dumps(ans)[:200]}")
R.check("C-30c control: the same order under the main network's domain is refused for its signature",
        sig_refused(rr.status_code, ans), f"HTTP {rr.status_code}")

c = vx.cancel_order(session.key.hex(), owner.address, 1)
print(f"  cancel answer: {json.dumps(c)[:200]}")
R.check("C-30d CancelOrder: judged on the order, not on the signature", not sig_refused(c.get("status_code"), c),
        f"HTTP {c.get('status_code')}")
sh = cancel_order_struct_hash(owner.address, 1)
d = keccak(b"\x19\x01" + domains.separator("VordCore", 101101, MAINNET_GENESIS) + sh)
sig = "0x" + Account.unsafe_sign_hash(d, session.key).signature.hex().removeprefix("0x")[:128]
rr = requests.post(rest + "/order/cancel", json=cancel_order_body(owner.address, session.address, 1, sig), timeout=15)
ans = rr.json() if rr.content else {}
print(f"  cancel control: {rr.status_code} {json.dumps(ans)[:200]}")
R.check("C-30e control: the cancel under the main network's domain is refused for its signature",
        sig_refused(rr.status_code, ans), f"HTTP {rr.status_code}")

try:
    st = sc.get_state(rest, owner.address)
    n0 = int(getattr(st, "next_nonce", 0) or 0) or int(time.time() * 1000)
except Exception:
    n0 = int(time.time() * 1000)
a1 = sc.submit(rest, owner.key.hex(), owner.address, int(time.time() * 1000) + 120_000, max(n0, int(time.time() * 1000)),
               network=net, timeout=15)
print(f"  stop-all answer: {a1}")
R.check("C-30f ScheduleCancel (stop-all) signed by the owner is accepted", a1.ok or not SIG.search(a1.reason),
        f"HTTP {a1.status_code} {a1.reason[:80]}")
time.sleep(3)
a2 = sc.clear(rest, owner.key.hex(), owner.address, int(time.time() * 1000) + 1, network=net, timeout=15)
R.check("C-30g ScheduleCancel clear is accepted", a2.ok or not SIG.search(a2.reason), f"HTTP {a2.status_code} {a2.reason[:80]}")

r = ops.revoke_session(wait_s=45)
R.check("C-30h SessionRevoke applied (the session is gone)", r.applied is True, f"{r.status_code} {str(r.answer)[:120]}")
R.finish()
