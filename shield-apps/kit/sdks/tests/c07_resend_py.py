"""C-14..C-17 (Python SDK): retry after a timeout never signs a second body and never places a second order.

A local node on 127.0.0.1 records every copy (it does not deduplicate) and answers the scripted way.
C-14 the first copy is taken but its answer is lost (a read timeout); the SDK sends again. Every copy must be the SAME
     bytes (same nonce, same signature), at most `retries` copies, and the answer "received" after a read-back.
C-15 two busy-gateway answers (503) then 200: the same bytes three times.
C-16 a write the network does NOT deduplicate (cancel-all): after a lost answer the SDK must NOT send it again; it
     reports "unknown" (one copy).
C-17 a new call after an unknown result takes a NEW nonce (a new intent), never the old signed bytes.

Run:  python3 this file   (pip install vordium; no network access)
Exit: 0 = defended, 1 = a second body was signed or a second order applied, 3 = cannot run.
"""
import json
import os
import sys
import threading
import warnings
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kit import TESTNET_GENESIS, Results, Stub, clean_env  # noqa: E402

warnings.simplefilter("ignore")
clean_env()
try:
    import vordium
    from eth_account import Account
    from vordium import units
    from vordium.dex import Vordex, BUY, LIMIT
    from vordium.mm import MarketMaker
except Exception as e:  # pragma: no cover
    print(f"cannot import vordium: {e}")
    sys.exit(3)

R = Results(f"C-14..C-17 resend after timeout, Python SDK vordium {vordium.__version__}")
OWNER, SESSION = Account.create(), Account.create()


class Chain:
    """Applies each (owner, clientNonce) once; plays a scripted list of behaviours per copy."""

    def __init__(self, script):
        self.script, self.copies, self.applied, self.lock = list(script), [], {}, threading.Lock()

    def place(self, h, raw):
        with self.lock:
            self.copies.append(raw)
            step = self.script.pop(0) if self.script else "ok"
            b = json.loads(raw)
            key = (b["owner"].lower(), int(b["clientNonce"]))
            first = key not in self.applied
            if step in ("ok", "slow-ok"):
                self.applied.setdefault(key, [])
                self.applied[key].append({"client_nonce": b["clientNonce"], "pair_id": b["pairId"], "side": b["side"],
                                     "size_18dec": b["size_18dec"],
                                     "price_8dec": str(int(Decimal(str(b["price"])) * 10 ** 8)), "order_id": 7})
        if step == "503":
            return (503, {"error": "busy"})
        if step == "slow-ok":
            return ("sleep", 2.5, 200, {"status": "submitted"})
        if not first:
            return (409, {"code": "nonce", "error": "nonce already used"})
        return (200, {"status": "submitted"})

    def orders(self, h, raw):
        return (200, [o for v in self.applied.values() for o in v])


def vordex(s):
    s.identity(101102, TESTNET_GENESIS)
    return Vordex(rpc_url=s.base, network="testnet", specs=units.NO_RULES, chain_clock=None, timeout=1)


def order(vx, retries=3):
    return vx.place_order(session_key=SESSION.key.hex(), owner=OWNER.address, pair_id=1, side=BUY, size="0.01",
                          price="1000", order_type=LIMIT, retries=retries)


# C-14
with Stub() as s:
    c = Chain(["slow-ok"])
    s.routes[("POST", "/order/place")] = c.place
    s.routes[("GET", f"/orders/{OWNER.address}")] = c.orders
    try:
        res = order(vordex(s))
        why = f"status={res.get('status')} already_received={res.get('already_received')} attempts={res.get('attempts')}"
    except Exception as e:
        res, why = {}, f"{type(e).__name__}: {str(e)[:120]}"
    same = len(set(c.copies)) == 1
    R.check("C-14 lost answer: every copy is the same bytes", same and len(c.copies) >= 2,
            f"{len(c.copies)} copies, {len(set(c.copies))} distinct bodies")
    R.check("C-14b at most `retries` (3) copies, all under one client nonce", len(c.copies) <= 3 and len(c.applied) == 1,
            f"{len(c.copies)} copies, {len(c.applied)} distinct nonce(s); {why}")
    R.check("C-14c the answer is 'received' after a read-back that matches what was signed",
            res.get("already_received") is True, why)
    first_nonce = json.loads(c.copies[0])["clientNonce"] if c.copies else None

# C-15
with Stub() as s:
    c = Chain(["503", "503", "ok"])
    s.routes[("POST", "/order/place")] = c.place
    s.routes[("GET", f"/orders/{OWNER.address}")] = c.orders
    try:
        res = order(vordex(s))
        why = f"status_code={res.get('status_code')} attempts={res.get('attempts')}"
    except Exception as e:
        why = f"{type(e).__name__}: {str(e)[:120]}"
    R.check("C-15 503, 503, 200: the same bytes each time", len(c.copies) == 3 and len(set(c.copies)) == 1,
            f"{len(c.copies)} copies, {len(set(c.copies))} distinct; {why}")

# C-16 cancel-all (not deduplicated by the network)
with Stub() as s:
    s.identity(101102, TESTNET_GENESIS)
    copies = []

    def cancel_all(h, raw):
        copies.append(raw)
        return ("sleep", 2.5, 200, {"status": "ok"})
    s.routes[("POST", "/order/cancel-all")] = cancel_all
    try:
        mm = MarketMaker(s.base, SESSION.key.hex(), OWNER.address, network="testnet", timeout=1, chain_clock=None)
        r = mm.cancel_all(0)
        why = f"ok={getattr(r, 'ok', None)} refusal={getattr(getattr(r, 'refusal', None), 'code', None)}"
    except Exception as e:
        why = f"{type(e).__name__}: {str(e)[:120]}"
    R.check("C-16 cancel-all after a lost answer: one copy only, result unknown", len(copies) == 1
            and "delivery_unknown" in why, f"{len(copies)} copies; {why}")

# C-17 a new intent after an unknown result takes a new nonce
with Stub() as s:
    c = Chain(["503", "503", "503", "ok"])
    s.routes[("POST", "/order/place")] = c.place
    s.routes[("GET", f"/orders/{OWNER.address}")] = c.orders
    vx = vordex(s)
    try:
        r1 = order(vx)
    except Exception:
        r1 = {}
    try:
        r2 = order(vx)
    except Exception:
        r2 = {}
    nonces_seen = [json.loads(b)["clientNonce"] for b in c.copies]
    first3, last = nonces_seen[:3], nonces_seen[3:] if len(nonces_seen) > 3 else []
    R.check("C-17 a new call takes a new nonce; the old signed bytes are never reused for it",
            len(set(first3)) == 1 and last and last[0] > first3[0] and c.copies[3] != c.copies[0],
            f"first call nonces {set(first3)}, second call {set(last)}")
R.finish()
