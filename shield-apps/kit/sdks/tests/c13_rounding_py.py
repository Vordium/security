"""C-26, C-28, C-29 (Python SDK): rounding of sizes and prices and hostile market rules.

C-26 over every test-network market (live public rules) and 4,000 random sizes/prices given as str, float and Decimal:
     a buy is never signed above the price given and a sell never below; the signed price is on the market's tick and the
     6-decimal step and within one step of the price given; the size is never rounded up and lands on the lot.
C-28 hostile market rules from a lying node (huge lot or tick, zero/negative/text tick, absurd minimum) never make the
     SDK sign a bigger size, a higher buy price or a lower sell price than the caller asked; they refuse or round safe.
C-29 the order body the SDK posts carries exactly the signed values (the chain rebuilds the digest from the body).

Run:  python3 this file   (pip install vordium; one public GET of the market rules, else built-in rules)
Exit: 0 = defended, 1 = a worse value was signed, 3 = cannot run.
"""
import copy
import json
import os
import random
import sys
import warnings
from decimal import Decimal, getcontext
from math import gcd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kit import TESTNET_GENESIS, Results, Stub, clean_env, live_specs  # noqa: E402

warnings.simplefilter("ignore")
clean_env()
getcontext().prec = 80
try:
    import vordium
    from eth_account import Account
    from vordium import units
    from vordium.dex import Vordex, BUY, SELL, LIMIT
except Exception as e:  # pragma: no cover
    print(f"cannot import vordium: {e}")
    sys.exit(3)

R = Results(f"C-26, C-28, C-29 rounding and hostile market rules, Python SDK vordium {vordium.__version__}")
specs = live_specs()
if specs is None:
    print("[note] the live market rules could not be read; using built-in rules")
    specs = {"specs": {"min_order_notional_6dec": "10000000", "pairs": [
        {"tick_8dec": t, "lot_18dec": l, "pair": {"pair_id": i, "name": f"M{i}", "symbol": f"M{i}", "active": True,
                                                 "min_size_18dec": "0", "kind": "perps"}}
        for i, (t, l) in enumerate([("10000000", "100000000000000"), ("10", "1000000000000000000"),
                                    ("1", "100000000000000000000"), ("100000", "1000000000000000")], start=1)]}}
by = units.specs_by_pair(specs)
rnd = random.Random(438)
lcm = lambda a, b: a * b // gcd(a, b)

bad = []
n = 0
acc_p = acc_s = n_s = 0
for pid, sp in by.items():
    tick = int(sp.tick_8dec or 0) or 1
    step = lcm(tick, 100)
    lot = int(sp.lot_18dec or 0) or 1
    for _ in range(4000 // max(1, len(by))):
        mag = rnd.choice([Decimal("0.00001234"), Decimal("0.0027967"), Decimal("1.5"), Decimal("97.123456789"),
                          Decimal("3123.4567891"), Decimal("64000.12345")])
        p = mag * (Decimal(1) + Decimal(rnd.randint(-5000, 5000)) / 10000)
        sz = Decimal(rnd.randint(1, 10 ** 6)) / Decimal(10 ** rnd.randint(0, 8)) * 100
        form = rnd.choice(["str", "float", "dec"])
        pin = str(p) if form == "str" else float(p) if form == "float" else p
        szin = str(sz) if form == "str" else float(sz) if form == "float" else sz
        exact_p = Decimal(repr(pin)) if isinstance(pin, float) else Decimal(str(pin))
        exact_s = Decimal(repr(szin)) if isinstance(szin, float) else Decimal(str(szin))
        for side in (BUY, SELL):
            n += 1
            try:
                p8 = units.price_8dec(pin, sp, "buy" if side == BUY else "sell")
            except Exception:
                continue                       # refused: never signed
            acc_p += 1
            got = Decimal(p8) / Decimal(10 ** 8)
            if side == BUY and got > exact_p or side == SELL and got < exact_p or p8 % step or \
                    abs(got - exact_p) >= Decimal(step) / Decimal(10 ** 8):
                bad.append(("price", pid, side, pin, p8))
        n_s += 1
        try:
            s18 = units.size_18dec(szin, sp)
        except Exception:
            continue
        acc_s += 1
        if Decimal(s18) / Decimal(10 ** 18) > exact_s or s18 % lot or exact_s - Decimal(s18) / Decimal(10 ** 18) >= Decimal(lot) / Decimal(10 ** 18):
            bad.append(("size", pid, szin, s18))
R.check("C-26 floor: most generated values are accepted, so the rounding checks are not vacuous",
        acc_p >= 0.8 * n and acc_s >= 0.8 * n_s, f"{acc_p}/{n} prices and {acc_s}/{n_s} sizes accepted")
R.check(f"C-26 {n} prices and sizes on {len(by)} markets: never worse than given, on the step", not bad,
        f"{len(bad)} bad, e.g. {bad[:2]}")

# C-28 + C-29 hostile market rules from the node, through the full order path
OWNER, SESSION = Account.create(), Account.create()
base = specs if "specs" in specs else {"specs": specs}
pair0 = next(p for p in base["specs"]["pairs"] if int(p["pair"]["pair_id"]) == min(by))
hostile = {
    "control (rules as published)": {},
    "huge lot": {"lot_18dec": str(10 ** 60)},
    "huge tick": {"tick_8dec": str(10 ** 30)},
    "zero tick": {"tick_8dec": "0"},
    "negative tick": {"tick_8dec": "-100"},
    "text tick": {"tick_8dec": "1e2; DROP"},
    "zero lot": {"lot_18dec": "0"},
    "absurd minimum size": {"pair": dict(pair0["pair"], min_size_18dec=str(10 ** 40))},
}
worse, posted_bodies = [], []
for label, patch in hostile.items():
    sp = copy.deepcopy(base)
    for p in sp["specs"]["pairs"]:
        if int(p["pair"]["pair_id"]) == min(by):
            p.update(patch)
    for side, price in ((BUY, "1000.123456789"), (SELL, "1000.123456789")):
        with Stub() as s:
            s.identity(101102, TESTNET_GENESIS)
            s.routes[("GET", "/markets/specs")] = sp
            s.routes[("POST", "/order/place")] = (200, {"status": "submitted"})
            try:
                Vordex(rpc_url=s.base, network="testnet", chain_clock=None, timeout=3).place_order(
                    session_key=SESSION.key.hex(), owner=OWNER.address, pair_id=min(by), side=side, size="0.5",
                    price=price, order_type=LIMIT, retries=1)
            except Exception:
                pass
            for r in s.log:
                if r["path"] == "/order/place":
                    b = json.loads(r["raw"])
                    posted_bodies.append(dict(b, _label=label))
                    bp, bs = Decimal(str(b["price"])), Decimal(b["size_18dec"]) / Decimal(10 ** 18)
                    if bs > Decimal("0.5") or (side == BUY and bp > Decimal(price)) or (side == SELL and bp < Decimal(price)):
                        worse.append((label, side, str(bp), str(bs)))
control_sent = sum(1 for b in posted_bodies if b.get("_label") == "control (rules as published)")
R.check("C-28 floor: the control order under the published rules is signed and sent (both sides)", control_sent == 2,
        f"{control_sent} control orders sent")
R.check("C-28 hostile market rules never make a worse order (bigger size, higher buy, lower sell)", not worse,
        f"{len(posted_bodies)} orders sent under hostile rules; worse: {worse[:3]}")

# C-29 the body carries the signed values: re-derive the digest from the posted body and recover the session key
from vordium.caps import place_order_struct_hash  # noqa: E402
from vordium import domains  # noqa: E402
from eth_utils import keccak  # noqa: E402
mism = 0
for b in posted_bodies:
    p8 = int((Decimal(str(b["price"])) * 10 ** 8).to_integral_exact())
    side = 0 if b["side"] == "buy" else 1
    sh = place_order_struct_hash(b["owner"], b["pairId"], side, int(b["size_18dec"]), p8, b["leverageBps"],
                                 1 if b["orderType"] == "Limit" else 0, b["reduceOnly"], b["clientNonce"], b["post_only"],
                                 b["trigger_price_8dec"], b["trigger_dir"])
    d = keccak(b"\x19\x01" + domains.separator("VordCore", 101102, TESTNET_GENESIS) + sh)
    sig = bytes.fromhex(b["signature"][2:])
    ok = any(Account._recover_hash(d, vrs=(v, int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:64], "big"))) ==
             SESSION.address for v in (27, 28))
    mism += 0 if ok else 1
R.check("C-29 every posted body re-derives to a digest the session key signed", posted_bodies and mism == 0,
        f"{len(posted_bodies)} bodies, {mism} mismatched")
R.finish()
