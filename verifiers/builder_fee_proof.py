#!/usr/bin/env python3
"""Builder-fee edge-case proof for the Vordium test network.

An app or bot (the *builder*) may add its own fee to the orders it sends for a trader, up to the rate the trader
approved. This script shows, with the public `vordium` SDK only, how the chain charges and accounts for that fee at
its edges:

  a  partial fills: one builder-fee limit order filled in two or more fills; each fill record carries its own builder
     fee, and their sum equals what the builder's stats read moved by
  b  rounding at the smallest amounts: the smallest order the market takes, with the smallest fee (1 cbps); each fill's
     exact fee (value x rate) against the fee charged, including a fill whose exact fee is below one 6-decimal unit
  c  the approved rate is a hard ceiling: an order at exactly the approved rate is accepted and charged that rate; one
     cbps more is refused (the chain's code); a fee of 0 and a fee above the market's cap are refused too
  d  "exhausted" approvals: (i) the account approves the most builders it may, and the next approval is refused;
     (ii) whether an approval carries any amount or budget at all
  e  an approval withdrawn (or lowered) while a builder-fee order rests on the book: what the chain charges when that
     order fills afterwards
  f  claim reconciliation: the builder's fees add up to claimed + unclaimed; a claim moves exactly the unclaimed amount

Two accounts are used: a TRADER (approves the builder and places the builder-fee orders) and a BUILDER (named on those
orders; it also places the plain counter-orders that fill the trader's resting orders, and claims its fees at the
end). Case d also needs up to 10 extra builder addresses: approvals need no funds, so these are fresh keys that hold
nothing (`--filler-key-dir`, made on first use).

TEST NETWORK ONLY. The script refuses any network other than the Vordium test network (chain id 101102). Keys are read
from files you name (mode 600); they are never printed or written anywhere. Without `--live` the script reads the
network, checks both accounts and stops (nothing is signed or sent).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import secrets
import stat
import sys
import threading
import time
import traceback
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

TESTNET_CHAIN_ID = 101102
SPEC_URL = "https://testnet.vordex.xyz/network-spec.json"
FAUCET_URL = "https://testnet.vordex.xyz/faucet"
UA = {"User-Agent": "vordium-builder-fee-proof/1", "Accept": "application/json", "Cache-Control": "no-store"}
HEX_KEY = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")
BUY, SELL = 0, 1
MARKET, LIMIT = 0, 1
FEE_DIV = 10 ** 6            # 1 cbps = one millionth of the filled value (1,000 cbps = 0.1 %)
NOTIONAL_DIV = 10 ** 20      # price (8 decimals) x size (18 decimals) -> USDC (6 decimals)


# ── output ───────────────────────────────────────────────────────────────────────────────────────────────────────────
class Log:
    def __init__(self, path: Path):
        self.fh = open(path, "a", encoding="utf-8")
        self.lock = threading.Lock()

    def __call__(self, *parts: Any) -> None:
        line = " ".join(str(p) for p in parts)
        stamp = time.strftime("%H:%M:%S", time.gmtime())
        with self.lock:
            print(f"[{stamp}] {line}", flush=True)
            self.fh.write(f"[{stamp}] {line}\n")
            self.fh.flush()


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: Optional[int] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime((ms or now_ms()) / 1000))


def shown(body: Dict[str, Any]) -> Dict[str, Any]:
    """A signed body for the record, with the signature shortened."""
    b = dict(body)
    if isinstance(b.get("signature"), str) and len(b["signature"]) > 20:
        b["signature"] = b["signature"][:10] + "…" + b["signature"][-6:]
    return b


# ── keys ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def read_key(path: str, what: str) -> str:
    p = Path(path).expanduser()
    if p.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SystemExit(f"{what} key file {p} can be read by other users: chmod 600 it first. Nothing was done.")
    k = p.read_text().strip()
    if not HEX_KEY.match(k):
        raise SystemExit(f"{what} key file {p} does not hold one 32-byte hex key. Nothing was done.")
    return k if k.startswith("0x") else "0x" + k


def new_key_file(f: Path) -> str:
    k = "0x" + secrets.token_hex(32)
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(k + "\n")
    return k


def make_keys(d: str) -> None:
    from eth_account import Account
    out = Path(d).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    for name in ("trader", "builder"):
        f = out / f"{name}.key"
        if f.exists():
            raise SystemExit(f"{f} exists; refusing to overwrite a key")
        print(f"{name}: {Account.from_key(new_key_file(f)).address}  ({f}, mode 600)")
    print(f"Fund BOTH trading accounts with test USDC at {FAUCET_URL} (the builder needs at least 100 USDC of "
          f"account value before orders may name it), then run with --live.")


def filler_keys(d: str, n: int) -> List[str]:
    """n keys in DIR (filler-01.key ...), made when missing. They only ever receive approvals: no funds needed."""
    out = Path(d).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    keys = []
    for i in range(1, n + 1):
        f = out / f"filler-{i:02d}.key"
        keys.append(read_key(str(f), "filler") if f.exists() else new_key_file(f))
    return keys


# ── the network ──────────────────────────────────────────────────────────────────────────────────────────────────────
class Net:
    def __init__(self, rest: str):
        self.rest = rest.rstrip("/")

    def get(self, path: str, timeout: float = 15) -> Any:
        r = requests.get(self.rest + path, headers=UA, timeout=timeout)
        try:
            return r.json()
        except ValueError:
            return {"_status": r.status_code, "_text": r.text[:300]}

    def post(self, path: str, body: Dict[str, Any], timeout: float = 15) -> Dict[str, Any]:
        t0 = now_ms()
        try:
            r = requests.post(self.rest + path, json=body, headers=UA, timeout=timeout)
            try:
                ans = r.json()
            except ValueError:
                ans = {"_text": r.text[:300]}
            code = r.status_code
        except requests.RequestException as e:
            code, ans = None, {"_error": f"{type(e).__name__}: {str(e)[:200]}"}
        return {"http_status": code, "answer": ans, "sent_at_ms": t0, "head_after": self.head()}

    def head(self) -> Optional[int]:
        try:
            return int(self.get("/status", 8).get("chain_head"))
        except Exception:
            return None

    def events(self, owner: str, limit: int = 100) -> List[Dict[str, Any]]:
        j = self.get(f"/events/account/{owner.lower()}?limit={limit}")
        return [e for e in (j.get("events") if isinstance(j, dict) else None) or [] if isinstance(e, dict)]

    def orders(self, owner: str) -> List[Dict[str, Any]]:
        j = self.get(f"/orders/{owner}")
        return [o for o in (j if isinstance(j, list) else []) if isinstance(o, dict)]

    def positions(self, owner: str) -> List[Dict[str, Any]]:
        j = self.get(f"/positions/{owner}")
        return [p for p in (j if isinstance(j, list) else []) if isinstance(p, dict)]

    def balance(self, owner: str) -> Dict[str, Any]:
        return self.get(f"/balance/{owner}")

    def approvals(self, user: str) -> Dict[str, Any]:
        return self.get(f"/builder/approvals/{user}")

    def stats(self, builder: str) -> Dict[str, Any]:
        return self.get(f"/builder/stats/{builder}")

    def top(self, pair_id: int):
        b = self.get(f"/orderbook/{pair_id}")
        bid = (b.get("bids_8dec") or [[None]])[0][0]
        ask = (b.get("asks_8dec") or [[None]])[0][0]
        return (int(bid) if bid else None), (int(ask) if ask else None)


# ── arithmetic ───────────────────────────────────────────────────────────────────────────────────────────────────────
def notional6(price8: int, size18: int) -> Fraction:
    return Fraction(int(price8) * int(size18), NOTIONAL_DIV)


def fee_exact(price8: int, size18: int, cbps: int) -> Fraction:
    return notional6(price8, size18) * cbps / FEE_DIV


def frac_s(x: Fraction) -> str:
    return f"{float(x):.6f}" if x.denominator != 1 else str(x.numerator)


def fill_row(f: Dict[str, Any], builder: str, cbps: Optional[int], payer: str) -> Dict[str, Any]:
    """One fill as the proof judges it: the fill's own builder key, verbatim, next to the exact fee."""
    bk = f.get("builder")
    side = None
    if str((f.get("taker") or {}).get("account") or "").lower() == payer.lower():
        side = "taker"
    elif str((f.get("maker") or {}).get("account") or "").lower() == payer.lower():
        side = "maker"
    charged = None
    if isinstance(bk, dict) and side and str(bk.get(f"{side}_builder") or "").lower() == builder.lower():
        charged = int(bk.get(f"{side}_fee_6dec") or 0)
    price8, size18 = int(f.get("price_8dec") or 0), int(f.get("size_18dec") or 0)
    row = {"fill_id": f.get("fill_id"), "height": f.get("height"), "price_8dec": price8, "size_18dec": str(size18),
           "trader_side": side, "notional_6dec_exact": frac_s(notional6(price8, size18)),
           "builder_key_verbatim": bk, "builder_fee_charged_6dec": charged,
           "trader_order_id": (f.get(side) or {}).get("order_id") if side else None}
    if cbps is not None:
        ex = fee_exact(price8, size18, cbps)
        row.update({"rate_cbps": cbps, "fee_exact_6dec": frac_s(ex), "fee_exact_below_one_unit": ex < 1,
                    "fee_rounded_up_6dec": math.ceil(ex), "fee_rounded_down_6dec": math.floor(ex),
                    "charged_equals_round_up": charged == math.ceil(ex) if charged is not None else None})
    return row


def by_step(rows: List[Dict[str, Any]], cbps: int) -> List[Dict[str, Any]]:
    """The fills of one trader order in one block, judged together. One match can be written as two fill records (a
    fill that closes a position and opens the other side is recorded as a closing part and an opening part); this
    shows whether the builder fee was charged on the whole match and on which records it is written."""
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["height"], r["trader_order_id"]), []).append(r)
    out = []
    for (h, oid), rs in groups.items():
        ex = sum((fee_exact(r["price_8dec"], int(r["size_18dec"]), cbps) for r in rs), Fraction(0))
        charged = sum(r["builder_fee_charged_6dec"] or 0 for r in rs)
        out.append({"height": h, "trader_order_id": oid, "fill_ids": [r["fill_id"] for r in rs],
                    "fee_exact_6dec": frac_s(ex), "charged_6dec": charged,
                    "charged_equals_round_up_of_whole": charged == math.ceil(ex),
                    "charged_equals_sum_of_per_record_round_up": charged == sum(math.ceil(fee_exact(
                        r["price_8dec"], int(r["size_18dec"]), cbps)) for r in rs),
                    "records_without_builder_key": [r["fill_id"] for r in rs if not isinstance(r["builder_key_verbatim"], dict)],
                    "records_whose_fee_is_not_their_own": [r["fill_id"] for r in rs if r.get("charged_equals_round_up") is False]})
    return out


# ── the proof ────────────────────────────────────────────────────────────────────────────────────────────────────────
class Proof:
    def __init__(self, a, log: Log, out: Path):
        self.a, self.log, self.out = a, log, out
        self.res: Dict[str, Any] = {"what": "Vordium testnet builder-fee edge-case proof", "network": "testnet",
                                    "started": iso(), "mode": "live" if a.live else "check-only", "cases": {}}
        self.fills_seen: Dict[Any, Dict[str, Any]] = {}     # every fill that named our builder, by fill id

    def case(self, key: str, data: Dict[str, Any]) -> None:
        self.res["cases"][key] = data
        self.save()

    def save(self) -> None:
        (self.out / "results.json").write_text(json.dumps(self.res, indent=2, default=str))

    # -- setup -----------------------------------------------------------------------------------------------------------
    def preflight(self) -> bool:
        import vordium
        from vordium import builder as b
        from vordium.dex import Vordex
        from eth_account import Account
        a, log = self.a, self.log
        spec = requests.get(SPEC_URL, headers=UA, timeout=15).json()
        if spec.get("testnet") is not True or int(spec.get("chainId", 0)) != TESTNET_CHAIN_ID:
            raise SystemExit("the network spec does not describe the test network (chain 101102). Nothing was done.")
        net = vordium.use_network("testnet")
        if net.chain_id != TESTNET_CHAIN_ID:
            raise SystemExit("the SDK resolved a network other than the test network. Nothing was done.")
        self.rest = vordium.api_base(net)
        self.net = Net(self.rest)
        self.b = b
        self.tk, self.bk = read_key(a.trader_key_file, "trader"), read_key(a.builder_key_file, "builder")
        self.T, self.B = Account.from_key(self.tk).address, Account.from_key(self.bk).address
        if self.T.lower() == self.B.lower():
            raise SystemExit("the trader and builder keys are the same key. Nothing was done.")
        self.dex = Vordex(self.rest)
        self.tops = b.BuilderOps(self.tk)
        self.bops = b.BuilderOps(self.bk)
        status = self.net.get("/status")
        mspec = self.net.get("/markets/specs")
        mspec = mspec.get("specs", mspec) if isinstance(mspec, dict) else {}
        row = next(p for p in mspec["pairs"] if p["pair"]["name"].upper() == a.market.upper())
        self.pair = int(row["pair"]["pair_id"])
        self.tick8, self.lot18 = int(row["tick_8dec"]), int(row["lot_18dec"])
        self.min_notional6 = int(mspec.get("min_order_notional_6dec") or 0)
        codes = self.net.get("/orders/codes")
        appr, st = self.net.approvals(self.T), self.net.stats(self.B)
        tb, bb = self.net.balance(self.T), self.net.balance(self.B)
        pre = {"sdk_version": vordium.__version__, "chain_id": net.chain_id, "genesis_sha256": status.get("genesis_sha256"),
               "rest": self.rest, "chain_head": status.get("chain_head"), "binary_sha8": status.get("binary_sha8"),
               "trading_open": status.get("trading_open"), "trader": self.T, "builder": self.B,
               "market": {"name": a.market.upper(), "pair_id": self.pair, "tick_8dec": self.tick8, "lot_18dec": self.lot18,
                          "min_order_notional_6dec": self.min_notional6},
               "trader_balance": tb, "builder_balance": bb, "trader_approvals": appr, "builder_stats": st,
               "trader_positions": self.net.positions(self.T), "builder_positions": self.net.positions(self.B),
               "builder_refusal_codes_published": codes.get("builder_refusal_codes")}
        log(f"network: test network, chain {net.chain_id}, head {status.get('chain_head')}, binary {status.get('binary_sha8')}")
        log(f"trader {self.T} available {tb.get('available')}; builder {self.B} available {bb.get('available')} (6-dec USDC)")
        log(f"builder fees active: {appr.get('active')}/{st.get('active')}; caps {st.get('caps_cbps')}; max approvals {appr.get('max')}")
        blocked = []
        if appr.get("active") is not True or st.get("active") is not True:
            blocked.append("builder fees are not active on the test network now (the reads say active is not true)")
        if int(tb.get("available") or 0) < a.min_usdc * 10 ** 6:
            blocked.append(f"the trader {self.T} has less than {a.min_usdc} test USDC available: claim test USDC at "
                           f"{FAUCET_URL} to its trading account")
        if st.get("account_value_ok") is not True or int(bb.get("available") or 0) < a.min_usdc * 10 ** 6:
            blocked.append(f"the builder {self.B} needs at least {int(st.get('min_account_value_6dec') or 0) // 10**6} "
                           f"USDC of account value (orders naming it are refused otherwise) and {a.min_usdc} USDC "
                           f"available for its counter-orders: claim test USDC at {FAUCET_URL} to its trading account")
        if a.live and (self.net.positions(self.T) or self.net.orders(self.T)):
            blocked.append("the trader holds a position or resting orders: close and cancel them first")
        if blocked:
            pre["blocked"] = blocked
            for x in blocked:
                log("REFUSED:", x)
        self.case("0_preflight", pre)
        return not blocked

    # -- small tools ------------------------------------------------------------------------------------------------------
    def nonce(self, owner: str) -> int:
        from vordium import nonces
        from vordium.mm import nonce_clock
        return nonces.fresh(nonce_clock(owner), 0, getattr(self.dex, "_chain", None))

    def deadline(self) -> int:
        return self.b.deadline(None, self.tops._now_s())

    def v3(self, fee: int, side: int, size18: int, price8: int, *, post_only: bool = False, builder: Optional[str] = None,
           order_type: int = LIMIT, worst8: int = 0, reduce_only: bool = False) -> Dict[str, Any]:
        """A builder-fee order of the trader, signed with the SDK's PlaceOrderV3 signer and sent as signed. The SDK's own
        pre-checks are skipped here on purpose, so the CHAIN's answer to each edge case is what is recorded."""
        n = self.nonce(self.T)
        s = self.b.place_order_v3(self.tk, self.T, self.pair, side, size18, price8, self.a.leverage * 10000, order_type,
                                  n, self.deadline(), builder or self.B, fee, self.dex.domain.separator(),
                                  post_only=post_only, worst_price_8dec=worst8, reduce_only=reduce_only)
        r = self.net.post("/order/place", s.body)
        r.update(client_nonce=n, signed=shown(s.body))
        return r

    def plain(self, key: str, owner: str, side: int, size18: int, price8: int, *, post_only=False,
              market=False) -> Dict[str, Any]:
        """A plain order (no builder) through the SDK: a limit order at price8, or a market order."""
        ans = self.dex.place_order(key, owner, self.pair, side, Decimal(size18) / 10 ** 18,
                                   None if market else Decimal(price8) / 10 ** 8, leverage=self.a.leverage,
                                   order_type=MARKET if market else LIMIT, post_only=post_only)
        return {"answer": ans, "client_nonce": ans.get("clientNonce"), "head_after": self.net.head()}

    def placed(self, owner: str, nonce: Any, wait_s: float = 10.0) -> Dict[str, Any]:
        """The chain's record of an order by client nonce: order_placed (id, height) or a refusal record."""
        end = time.time() + wait_s
        while True:
            evs = [e for e in self.net.events(owner) if str(e.get("client_nonce")) == str(nonce)]
            pl = next((e for e in evs if e.get("kind") == "order_placed"), None)
            if pl:
                return {"order_id": pl.get("order_id"), "height": pl.get("height"), "order_placed": pl,
                        "closed": [e for e in evs if e.get("kind") == "order_closed"]}
            other = [e for e in evs if e.get("kind") != "order_placed"]
            if other or time.time() >= end:
                return {"order_id": None, "events": evs,
                        "note": None if other else f"no record carries client nonce {nonce} after {wait_s:g} s"}
            time.sleep(0.5)

    def events_since(self, owner: str, height: int) -> List[Dict[str, Any]]:
        """Every record of the account at or after ``height`` (the read pages backwards with ``cursor``)."""
        out, cursor = [], None
        for _ in range(50):
            j = self.net.get(f"/events/account/{owner.lower()}?limit=100" + (f"&cursor={cursor}" if cursor else ""))
            evs = [e for e in (j.get("events") if isinstance(j, dict) else None) or [] if isinstance(e, dict)]
            out += [e for e in evs if int(e.get("height") or 0) >= height]
            cursor = j.get("next_cursor") if isinstance(j, dict) else None
            if not evs or not cursor or min(int(e.get("height") or 0) for e in evs) < height:
                break
        return out

    def builder_fills_since(self, height: int) -> List[Dict[str, Any]]:
        """Every fill of the trader at or after ``height`` whose builder key names our builder, oldest first."""
        fs = {e.get("fill_id"): e for e in self.events_since(self.T, height) if e.get("kind") == "fill"
              and isinstance(e.get("builder"), dict)
              and self.B.lower() in (str(e["builder"].get("taker_builder") or "").lower(),
                                     str(e["builder"].get("maker_builder") or "").lower())}
        return sorted(fs.values(), key=lambda e: (e.get("height") or 0, e.get("fill_id") or 0))

    def fills_of(self, owner: str, oid: Any) -> List[Dict[str, Any]]:
        out = []
        for e in self.net.events(owner):
            if e.get("kind") == "fill" and oid in ((e.get("taker") or {}).get("order_id"), (e.get("maker") or {}).get("order_id")):
                out.append(e)
        return sorted(out, key=lambda e: (e.get("height") or 0, e.get("fill_id") or 0))

    def wait_fills(self, owner: str, oid: Any, size18: int, wait_s: float = 15.0) -> List[Dict[str, Any]]:
        end = time.time() + wait_s
        while True:
            fs = self.fills_of(owner, oid)
            if sum(int(f.get("size_18dec") or 0) for f in fs) >= size18 or time.time() >= end:
                for f in fs:
                    if isinstance(f.get("builder"), dict):
                        self.fills_seen[f.get("fill_id")] = f
                return fs
            time.sleep(0.7)

    def inside_ask(self, wait_s: float = 30.0) -> Optional[Dict[str, int]]:
        """A price a sell can rest at without trading and be the best ask: the mark price on the price step, held
        strictly between the best bid and the best ask. (Kept near the mark: on the test network a buy and a sell at the
        same price well away from the mark were seen resting side by side without trading.)"""
        end = time.time() + wait_s
        while True:
            bid, ask = self.net.top(self.pair)
            mark8 = int(self.net.get(f"/oracle/{self.pair}").get("mark_price") or 0) * 100
            if bid and ask and mark8 and ask - bid >= 2 * self.tick8:
                p8 = min(max(mark8 // self.tick8 * self.tick8, bid + self.tick8), ask - self.tick8)
                return {"best_bid_8dec": bid, "best_ask_8dec": ask, "mark_8dec": mark8, "price_8dec": p8}
            if time.time() >= end:
                return None
            time.sleep(1)

    def min_size18(self, price8: int) -> int:
        need = -(-self.min_notional6 * NOTIONAL_DIV // price8)
        return -(-need // self.lot18) * self.lot18

    def cancel_all(self, key: str, owner: str) -> List[Dict[str, Any]]:
        done = []
        for o in self.net.orders(owner):
            oid = o.get("id", o.get("order_id"))
            if oid is not None:
                done.append({"order_id": oid, "answer": self.dex.cancel_order(key, owner, int(oid))})
        if done:
            time.sleep(1.5)
        return done

    def approve(self, builder: str, cbps: int) -> Dict[str, Any]:
        """ApproveBuilderFee signed with the SDK's signer and sent as signed (cbps 0 = revoke); then the chain's read."""
        before = self.net.approvals(self.T)
        n = int(before.get("nonce") or 0) + 1
        s = self.b.approve_builder_fee(self.tk, self.T, builder, cbps, n, self.deadline(), self.tops.separator("VordCore"))
        r = self.net.post("/builder/approve", s.body)
        end = time.time() + (20 if (r["http_status"] or 0) < 400 else 0)
        after = self.net.approvals(self.T)
        while time.time() < end:
            after = self.net.approvals(self.T)
            if int(after.get("nonce") or 0) >= n:
                break
            time.sleep(0.7)
        row = self.b.approval_of(after, builder)
        return {"builder": builder, "max_fee_cbps_signed": cbps, "nonce_signed": n, "http_status": r["http_status"],
                "answer": r["answer"], "head_after": r["head_after"], "approval_nonce_after": after.get("nonce"),
                "applied": int(after.get("nonce") or 0) >= n and (row == cbps if cbps else row is None),
                "approval_row_after": row, "count_after": after.get("count"), "max": after.get("max"),
                "read_height": after.get("head_height"), "signed": shown(s.body)}

    def counter_fill(self, rest_oid: Any, rest_size18: int, price8: int, sizes18: List[int]) -> Dict[str, Any]:
        """The builder account sends plain market buys, one per size, back to back (the resting sell is the best ask, so
        they take it); then the fills of the resting order are read. Market orders are used because a crossing LIMIT
        order was seen resting beside the order it crosses on the test network, matched only when a later order came."""
        sent = [(sz, self.plain(self.bk, self.B, BUY, sz, price8, market=True)) for sz in sizes18]
        fills = self.wait_fills(self.T, rest_oid, sum(sizes18))
        for _ in range(2):          # the book moved and another seller took the counter-order: try again for what is left
            left = next((int(o.get("remaining_18dec") or 0) for o in self.net.orders(self.T)
                         if o.get("id") == rest_oid), 0)
            if not left:
                break
            sent.append((left, self.plain(self.bk, self.B, BUY, left, price8, market=True)))
            fills = self.wait_fills(self.T, rest_oid, rest_size18)
        steps = []
        for sz, c in sent:
            cp = self.placed(self.B, c["client_nonce"])
            steps.append({"counter_size_18dec": str(sz), "counter_answer": c["answer"], "counter_order": cp.get("order_id"),
                          "counter_height": cp.get("height")})
        steps.append({"counter_leftovers_cancelled": self.cancel_all(self.bk, self.B)})
        return {"steps": steps, "fills": self.wait_fills(self.T, rest_oid, rest_size18, 3) or fills}

    def resting_sell(self, fee: int, size18: int) -> Dict[str, Any]:
        px = self.inside_ask()
        if px is None:
            return {"error": "the book's spread is one price step wide, so no order can rest alone at the best ask"}
        r = self.v3(fee, SELL, size18, px["price_8dec"], post_only=True)
        pl = self.placed(self.T, r["client_nonce"])
        return {"book": px, "intake": r, "placed": pl, "order_id": pl.get("order_id"), "price_8dec": px["price_8dec"]}

    # -- a ---------------------------------------------------------------------------------------------------------------
    def case_a(self):
        log, fee = self.log, self.a.fee_a
        out: Dict[str, Any] = {"what": "one builder-fee limit order filled in two or more fills, as taker (a1: one order "
                                       "takes two resting orders) and as maker (a2: one resting order taken twice)"}
        out["approve"] = self.approve(self.B, fee)
        s0 = self.net.stats(self.B)
        out["builder_stats_before"] = s0
        rows: List[Dict[str, Any]] = []
        # a1: the builder account rests two sells at the mark, inside the spread; the trader's builder-fee buy takes both
        px = self.inside_ask()
        if px is None:
            out["a1_taker"] = {"status": "not_run", "why": "the book's spread is one price step wide"}
        else:
            p8 = px["price_8dec"]
            mn = self.min_size18(p8)
            legs = []
            for sz in (mn + self.lot18, mn + 3 * self.lot18):
                c = self.plain(self.bk, self.B, SELL, sz, p8, post_only=True)
                legs.append({"size_18dec": str(sz), "answer": c["answer"], "client_nonce": c["client_nonce"]})
            tot_sz = sum(int(x["size_18dec"]) for x in legs)
            w8 = p8 + 20 * self.tick8          # a market buy with a worst price 20 steps above the two resting sells
            r = self.v3(fee, BUY, tot_sz, w8, order_type=MARKET, worst8=w8)
            pl = self.placed(self.T, r["client_nonce"])
            fs = self.wait_fills(self.T, pl.get("order_id"), tot_sz) if pl.get("order_id") else []
            for x in legs:
                x["placed"] = {k: v for k, v in self.placed(self.B, x["client_nonce"], 3).items() if k != "events"}
            a1 = {"book": px, "builder_account_resting_sells": legs, "trader_buy": {"intake": r, "placed": pl},
                  "fills": [fill_row(f, self.B, fee, self.T) for f in fs],
                  "cancelled_after": {"trader": self.cancel_all(self.tk, self.T), "builder": self.cancel_all(self.bk, self.B)}}
            out["a1_taker"] = a1
            rows += a1["fills"]
        # a2: the trader rests one builder-fee sell at the mark, inside the spread; the builder account takes it in two pieces
        px = self.inside_ask()
        if px is None:
            out["a2_maker"] = {"status": "not_run", "why": "the book's spread is one price step wide"}
        else:
            size = self.min_size18(px["price_8dec"]) * 2 + 3 * self.lot18
            rest = self.resting_sell(fee, size)
            a2: Dict[str, Any] = {"resting_order": rest}
            if rest.get("order_id"):
                first = self.min_size18(rest["price_8dec"]) + self.lot18
                cf = self.counter_fill(rest["order_id"], size, rest["price_8dec"], [first, size - first])
                a2["counter_orders"] = cf["steps"]
                a2["fills"] = [fill_row(f, self.B, fee, self.T) for f in cf["fills"]]
                a2["cancelled_after"] = self.cancel_all(self.tk, self.T)
                rows += a2["fills"]
            out["a2_maker"] = a2
        time.sleep(1.5)
        s1 = self.net.stats(self.B)
        out["builder_stats_after"] = s1
        tot = sum(r["builder_fee_charged_6dec"] or 0 for r in rows)
        d_fees = int(s1["fees_6dec"]) - int(s0["fees_6dec"])
        d_vol = int(s1["volume_6dec"]) - int(s0["volume_6dec"])
        n1 = len((out.get("a1_taker") or {}).get("fills") or [])
        n2 = len((out.get("a2_maker") or {}).get("fills") or [])
        out["by_step"] = by_step(rows, fee)
        out["check"] = {"a1_fills_of_one_taker_order": n1, "a2_fills_of_one_resting_order": n2,
                        "per_fill_builder_fees_6dec": [r["builder_fee_charged_6dec"] for r in rows],
                        "sum_fill_builder_fees_6dec": tot, "stats_fees_delta_6dec": d_fees,
                        "stats_volume_delta_6dec": d_vol,
                        "sum_fill_notional_6dec_floor": sum(int(notional6(r["price_8dec"], int(r["size_18dec"]))) for r in rows),
                        "every_fill_has_builder_key": all(isinstance(r["builder_key_verbatim"], dict) for r in rows),
                        "every_fill_rounded_up": all(r["charged_equals_round_up"] for r in rows),
                        "sum_equals_stats_delta": tot == d_fees}
        ok = (n1 >= 2 or n2 >= 2) and tot == d_fees and out["check"]["every_fill_has_builder_key"] and bool(rows)
        out["status"] = "as_expected" if ok else "unexpected"
        log(f"a: taker order {n1} fills, resting order {n2} fills; per-fill builder fees "
            f"{out['check']['per_fill_builder_fees_6dec']} sum {tot}; stats fees moved {d_fees} -> {out['status']}")
        self.case("a_partial_fills", out)

    # -- b ---------------------------------------------------------------------------------------------------------------
    def case_b(self):
        log, fee = self.log, 1
        out: Dict[str, Any] = {"what": "smallest order and smallest fee (1 cbps); exact fee against the fee charged"}
        h0 = self.net.head() or 0
        out["approve"] = self.approve(self.B, max(self.a.fee_a, fee))
        s0 = self.net.stats(self.B)
        out["builder_stats_before"] = s0
        # b1: a market order of one size step (far below the smallest order value), with a builder fee
        bid, ask = self.net.top(self.pair)
        worst = ask + 20 * self.tick8 if ask else 0
        r = self.v3(fee, BUY, self.lot18, worst, order_type=MARKET, worst8=worst)
        pl = self.placed(self.T, r["client_nonce"], 8)
        b1 = {"what": "a market buy of one size step with a 1 cbps builder fee", "size_18dec": str(self.lot18),
              "intake": r, "placed": pl}
        if pl.get("order_id"):
            b1["fills"] = [fill_row(f, self.B, fee, self.T) for f in self.wait_fills(self.T, pl["order_id"], self.lot18, 10)]
        b1["outcome"] = ("refused: " + str((r["answer"] or {}).get("code"))) if (r["http_status"] or 0) >= 400 else (
            "filled" if b1.get("fills") else "accepted, no fill seen")
        out["b1_market_one_step"] = b1
        # b2: the builder account rests a sell of (smallest size + one step) at the mark, inside the spread; the trader buys
        # the smallest size with a 1 cbps fee (one fill), then buys the smallest size again: only the one-step remainder
        # is there to fill, so that fill is worth well under one USDC and its exact fee is below one 6-dec unit.
        px = self.inside_ask()
        if px is None:
            out["b2"] = {"status": "not_run", "why": "the spread is one price step wide"}
        else:
            p8 = px["price_8dec"]
            mn = self.min_size18(p8)
            c = self.plain(self.bk, self.B, SELL, mn + self.lot18, p8, post_only=True)
            cp = self.placed(self.B, c["client_nonce"])
            b2: Dict[str, Any] = {"book": px, "smallest_size_18dec": str(mn), "builder_account_resting_sell": {
                "answer": c["answer"], "order_id": cp.get("order_id"), "height": cp.get("height"),
                "size_18dec": str(mn + self.lot18)}}
            legs = []
            for i, sz in enumerate((mn, mn)):
                w8 = p8 + 20 * self.tick8
                r = self.v3(fee, BUY, sz, w8, order_type=MARKET, worst8=w8)
                pl = self.placed(self.T, r["client_nonce"])
                fs = self.wait_fills(self.T, pl.get("order_id"), sz if i == 0 else self.lot18, 10) if pl.get("order_id") else []
                legs.append({"trader_buy_size_18dec": str(sz), "intake": r, "placed": pl,
                             "fills": [fill_row(f, self.B, fee, self.T) for f in fs]})
            b2["trader_buys"] = legs
            b2["cancelled_after"] = {"trader": self.cancel_all(self.tk, self.T), "builder": self.cancel_all(self.bk, self.B)}
            out["b2_smallest_then_remainder"] = b2
        time.sleep(1.5)
        s1 = self.net.stats(self.B)
        out["builder_stats_after"] = s1
        rows = (out["b1_market_one_step"].get("fills") or []) + [
            f for leg in (out.get("b2_smallest_then_remainder") or {}).get("trader_buys", []) for f in leg["fills"]]
        seen = {r["fill_id"] for r in rows}
        rows += [fill_row(f, self.B, fee, self.T) for f in self.builder_fills_since(h0) if f.get("fill_id") not in seen]
        tot = sum(r["builder_fee_charged_6dec"] or 0 for r in rows)
        d_fees = int(s1["fees_6dec"]) - int(s0["fees_6dec"])
        sub = [r for r in rows if r.get("fee_exact_below_one_unit")]
        out["by_step"] = by_step(rows, fee)
        out["check"] = {"fills": len(rows), "sum_fill_builder_fees_6dec": tot, "stats_fees_delta_6dec": d_fees,
                        "sum_equals_stats_delta": tot == d_fees,
                        "every_fill_rounded_up": all(r["charged_equals_round_up"] for r in rows) if rows else None,
                        "fills_with_exact_fee_below_one_unit": [
                            {"fill_id": r["fill_id"], "exact": r["fee_exact_6dec"], "charged": r["builder_fee_charged_6dec"]}
                            for r in sub]}
        ok = bool(rows) and tot == d_fees and all(r["charged_equals_round_up"] for r in rows) and bool(sub)
        out["status"] = "as_expected" if ok else "unexpected"
        log(f"b: market one-step -> {out['b1_market_one_step']['outcome']}; fills {[(r['fee_exact_6dec'], r['builder_fee_charged_6dec']) for r in rows]}"
            f" -> {out['status']}")
        self.case("b_rounding_smallest", out)

    # -- c ---------------------------------------------------------------------------------------------------------------
    def sdk_refusal(self, fn: Callable[[], Any]) -> Dict[str, Any]:
        try:
            ans = fn()
            return {"sdk_refused_before_signing": False, "answer": ans}
        except self.b.BuilderError as e:
            return {"sdk_refused_before_signing": True, "code": e.code, "message": str(e)}

    def far_bid8(self) -> int:
        bid, _ = self.net.top(self.pair)
        return (bid * 9 // 10) // self.tick8 * self.tick8

    def case_c(self):
        log, X = self.log, self.a.fee_c
        out: Dict[str, Any] = {"what": f"approval at {X} cbps: an order at exactly {X} is accepted and charged {X}; "
                                       f"{X + 1} is refused"}
        st = self.net.stats(self.B)
        cap = int(st["caps_cbps"]["perps"])
        far = self.far_bid8()
        size_far = self.min_size18(far) + self.lot18
        # c0: the market's cap binds even when the approval is higher
        out["c0_approve_above_perps_cap"] = self.approve(self.B, cap + 500)
        c0 = self.v3(cap + 1, BUY, size_far, far, post_only=True)
        out["c0_order_above_perps_cap"] = {"fee_cbps": cap + 1, "perps_cap_cbps": cap, "intake": c0,
                                          "sdk_check": self.sdk_refusal(lambda: self.b.check_fee(cap + 1, "perps", st["caps_cbps"]))}
        # c1: approve X, order at X+1 (refused), at 0 (refused), at X (accepted, then filled)
        out["approve"] = self.approve(self.B, X)
        r = self.v3(X + 1, BUY, size_far, far, post_only=True)
        out["c1_order_above_approval"] = {"fee_cbps": X + 1, "intake": r, "sdk_check": self.sdk_refusal(
            lambda: self.dex.place_order(self.tk, self.T, self.pair, BUY, Decimal(size_far) / 10**18, Decimal(far) / 10**8,
                                         leverage=self.a.leverage, order_type=LIMIT, post_only=True,
                                         builder={"address": self.B, "fee_cbps": X + 1}))}
        r0 = self.v3(0, BUY, size_far, far, post_only=True)
        out["c2_order_fee_zero"] = {"fee_cbps": 0, "intake": r0}
        s0 = self.net.stats(self.B)
        size = self.min_size18(far) + 7 * self.lot18
        rest = self.resting_sell(X, size)
        out["c3_order_at_approval"] = rest
        if rest.get("order_id"):
            cf = self.counter_fill(rest["order_id"], size, rest["price_8dec"], [size])
            out["c3_counter"] = cf["steps"]
            out["c3_fills"] = [fill_row(f, self.B, X, self.T) for f in cf["fills"]]
        time.sleep(1.5)
        s1 = self.net.stats(self.B)
        out["builder_stats_before_after_c3"] = [s0, s1]
        out["leftovers_cancelled"] = self.cancel_all(self.tk, self.T)
        code = lambda x: (x.get("answer") or {}).get("code") if isinstance(x.get("answer"), dict) else None
        fills = out.get("c3_fills") or []
        steps = by_step(fills, X)
        out["c3_by_step"] = steps
        out["check"] = {"above_cap_code": code(c0), "above_approval_code": code(r), "fee_zero_code": code(r0),
                        "at_approval_accepted": bool(rest.get("order_id")),
                        "at_approval_fills": len(fills),
                        "at_approval_charged_rate_cbps": X if steps and all(g["charged_equals_round_up_of_whole"] for g in steps) else None,
                        "every_record_carries_its_own_fee": all(f["charged_equals_round_up"] for f in fills),
                        "sum_fill_builder_fees_6dec": sum(f["builder_fee_charged_6dec"] or 0 for f in fills),
                        "stats_fees_delta_6dec": int(s1["fees_6dec"]) - int(s0["fees_6dec"])}
        ok = (code(r) == "builder_fee_above_approved" and code(r0) == "builder_fee_zero"
              and code(c0) == "builder_fee_above_cap" and bool(fills)
              and all(g["charged_equals_round_up_of_whole"] for g in steps)
              and out["check"]["sum_fill_builder_fees_6dec"] == out["check"]["stats_fees_delta_6dec"])
        out["status"] = "as_expected" if ok else "unexpected"
        if not out["check"]["every_record_carries_its_own_fee"]:
            out["finding"] = ("one match was written as more than one fill record, and the builder fee of the whole match "
                              "is written on one record; the other record has no builder key (see c3_by_step)")
        log(f"c: above cap -> {code(c0)}; {X + 1} -> {code(r)}; 0 -> {code(r0)}; {X} -> accepted={bool(rest.get('order_id'))}, "
            f"{len(fills)} fill(s) charged {[f['builder_fee_charged_6dec'] for f in fills]} -> {out['status']}")
        self.case("c_approval_max_rate", out)

    # -- d ---------------------------------------------------------------------------------------------------------------
    def case_d(self):
        from eth_account import Account
        log = self.log
        out: Dict[str, Any] = {"what": "(i) every approval slot filled, the next approval refused; (ii) does an approval "
                                       "carry any amount or budget"}
        appr = self.net.approvals(self.T)
        most = int(appr["max"])
        fillers = [Account.from_key(k).address for k in filler_keys(self.a.filler_key_dir, most)]
        out["max_approvals"] = most
        out["fillers"] = fillers
        out["filler_stats_example"] = self.net.stats(fillers[0])
        rows = []
        for f in fillers:
            if int(self.net.approvals(self.T)["count"]) >= most:
                break
            rows.append(self.approve(f, 5))
        out["fill_slots"] = [{k: r[k] for k in ("builder", "http_status", "applied", "count_after", "read_height")} for r in rows]
        full = self.net.approvals(self.T)
        out["approvals_when_full"] = full
        nxt = next(f for f in fillers if self.b.approval_of(full, f) is None)
        out["next_approval_sdk_check"] = self.sdk_refusal(lambda: self.tops.approve_builder_fee(nxt, 5))
        out["next_approval_chain"] = self.approve(nxt, 5)
        out["replace_when_full"] = self.approve(self.B, self.a.fee_c + 1)
        # an order naming an approved builder that holds no funds
        far = self.far_bid8()
        filler_in = next(f for f in fillers if self.b.approval_of(full, f) is not None)
        r = self.v3(5, BUY, self.min_size18(far) + self.lot18, far, post_only=True, builder=filler_in)
        out["order_naming_unfunded_builder"] = {"builder": filler_in, "builder_stats": self.net.stats(filler_in), "intake": r}
        # (ii) the approval's shape: every field the chain keeps per approval
        row_keys = sorted({k for a in full.get("approvals") or [] for k in a})
        out["approval_row_fields"] = row_keys
        out["revoke_fillers"] = [{"builder": f, "applied": self.approve(f, 0)["applied"]} for f in fillers
                                 if self.b.approval_of(self.net.approvals(self.T), f) is not None]
        out["approvals_after"] = self.net.approvals(self.T)
        nca = out["next_approval_chain"]
        code = lambda x: (x.get("answer") or {}).get("code") if isinstance(x.get("answer"), dict) else None
        out["check"] = {"count_when_full": full.get("count"), "max": most,
                        "next_approval_http_status": nca["http_status"], "next_approval_code": code(nca),
                        "next_approval_applied": nca["applied"], "count_after_next": nca["count_after"],
                        "replace_when_full_applied": out["replace_when_full"]["applied"],
                        "unfunded_builder_order_code": code(r),
                        "approval_has_amount_or_budget_field": any(k not in ("builder", "max_fee_cbps") for k in row_keys)}
        ok = (full.get("count") == most and not nca["applied"] and out["replace_when_full"]["applied"])
        out["status"] = "as_expected" if ok else "unexpected"
        log(f"d: {full.get('count')}/{most} approved; next -> http {nca['http_status']} code {code(nca)} applied {nca['applied']}; "
            f"replace when full applied {out['replace_when_full']['applied']}; unfunded builder order -> {code(r)}; "
            f"approval fields {row_keys} -> {out['status']}")
        self.case("d_exhausted_approval", out)

    # -- e ---------------------------------------------------------------------------------------------------------------
    def case_e(self):
        log, fee = self.log, self.a.fee_e
        out: Dict[str, Any] = {"what": "a builder-fee order resting on the book when its approval is withdrawn or lowered"}
        variants = []
        for name, change_to in (("unchanged (control)", fee), ("revoked", 0), ("lowered", max(1, fee // 4))):
            v: Dict[str, Any] = {"variant": name, "order_fee_cbps": fee, "approval_changed_to_cbps": change_to}
            v["approve"] = self.approve(self.B, fee)
            px = self.inside_ask()
            if px is None:
                v.update(status="not_run", why="the book's spread is one price step wide")
                variants.append(v)
                continue
            size = self.min_size18(px["price_8dec"]) + 2 * self.lot18
            rest = self.resting_sell(fee, size)
            v["resting_order"] = rest
            if not rest.get("order_id"):
                v["status"] = "not_run"
                variants.append(v)
                continue
            v["approval_change"] = self.approve(self.B, change_to)
            still = [o for o in self.net.orders(self.T) if o.get("id") == rest["order_id"]]
            v["resting_after_change"] = {"still_on_book": bool(still), "order": still[0] if still else None,
                                         "records": self.placed(self.T, rest["intake"]["client_nonce"], 1)}
            if name == "revoked":
                far = self.far_bid8()
                v["new_order_after_revoke"] = self.v3(fee, BUY, self.min_size18(far) + self.lot18, far, post_only=True)
            s0 = self.net.stats(self.B)
            cf = self.counter_fill(rest["order_id"], size, rest["price_8dec"], [size])
            v["counter"] = cf["steps"]
            v["fills"] = [fill_row(f, self.B, fee, self.T) for f in cf["fills"]]
            time.sleep(1.5)
            s1 = self.net.stats(self.B)
            v["builder_stats_before_after_fill"] = [s0, s1]
            charged = [f["builder_fee_charged_6dec"] for f in v["fills"]]
            v["outcome"] = {
                "fills": len(v["fills"]), "charged_6dec": charged,
                "fee_at_signed_rate": [f["fee_rounded_up_6dec"] for f in v["fills"]],
                "fee_at_changed_rate": [math.ceil(fee_exact(f["price_8dec"], int(f["size_18dec"]), change_to)) for f in v["fills"]],
                "stats_fees_delta_6dec": int(s1["fees_6dec"]) - int(s0["fees_6dec"])}
            if v["fills"]:
                if all(c is None for c in charged):
                    v["finding"] = f"no builder fee was charged on the fill after the approval was {name}"
                elif charged == v["outcome"]["fee_at_signed_rate"]:
                    v["finding"] = (f"the resting order kept charging the rate it was signed with ({fee} cbps) after the "
                                    f"approval was {name} (to {change_to} cbps)")
                elif charged == v["outcome"]["fee_at_changed_rate"]:
                    v["finding"] = f"the fill was charged the new approved rate ({change_to} cbps)"
                else:
                    v["finding"] = "the fill was charged an amount that matches neither rate"
            variants.append(v)
            self.cancel_all(self.tk, self.T)
        out["variants"] = variants
        code = lambda x: (x.get("answer") or {}).get("code") if isinstance(x, dict) and isinstance(x.get("answer"), dict) else None
        out["check"] = {v["variant"]: {"still_on_book_after_change": (v.get("resting_after_change") or {}).get("still_on_book"),
                                       "finding": v.get("finding"), "charged_6dec": (v.get("outcome") or {}).get("charged_6dec")}
                        for v in variants}
        out["check"]["new_order_after_revoke_code"] = next((code(v.get("new_order_after_revoke")) for v in variants
                                                            if v["variant"] == "revoked"), None)
        def charged_as(v, rate):
            return bool(v.get("fills")) and all((f["builder_fee_charged_6dec"] or 0) == (
                math.ceil(fee_exact(f["price_8dec"], int(f["size_18dec"]), rate)) if rate else 0) for f in v["fills"])
        by = {v["variant"].split()[0]: v for v in variants}
        if any(not v.get("fills") for v in variants):
            out["status"] = "incomplete"
        elif charged_as(by["unchanged"], fee) and charged_as(by["revoked"], 0) and charged_as(by["lowered"], 0):
            out["status"] = "as_observed: fee charged while approved; no fee after the approval was withdrawn or lowered below the order's fee"
        elif charged_as(by["revoked"], fee) or charged_as(by["lowered"], fee):
            out["status"] = "signed_rate_charged_after_approval_change"
        else:
            out["status"] = "other (see variants)"
        for v in variants:
            log(f"e/{v['variant']}: still on book {(v.get('resting_after_change') or {}).get('still_on_book')}; "
                f"{v.get('finding')}")
        log(f"e: new order after revoke -> {out['check']['new_order_after_revoke_code']}")
        self.case("e_approval_changed_mid_order", out)

    # -- cleanup + f ------------------------------------------------------------------------------------------------------
    def close_all(self, key: str, owner: str) -> List[Dict[str, Any]]:
        closes = []
        for pos in self.net.positions(owner):
            size = int(pos.get("size") or 0)
            if int(pos.get("pair_id") or 0) != self.pair or size <= 0:
                continue
            long_ = bool(pos.get("is_long", True))
            ans = self.dex.place_order(key, owner, self.pair, SELL if long_ else BUY, Decimal(size) / 10 ** 18, None,
                                       leverage=self.a.leverage, order_type=MARKET, reduce_only=True)
            closes.append({"size_18dec": str(size), "long": long_, "answer": ans})
        if closes:
            end = time.time() + 20
            while time.time() < end and self.net.positions(owner):
                time.sleep(1)
        return closes

    def cleanup(self) -> Dict[str, Any]:
        out = {"trader_cancels": self.cancel_all(self.tk, self.T), "builder_cancels": self.cancel_all(self.bk, self.B),
               "trader_closes": self.close_all(self.tk, self.T), "builder_closes": self.close_all(self.bk, self.B)}
        out.update(trader_positions_after=self.net.positions(self.T), builder_positions_after=self.net.positions(self.B),
                   trader_orders_after=self.net.orders(self.T), builder_orders_after=self.net.orders(self.B))
        return out

    def case_f(self, s_start: Dict[str, Any]):
        log = self.log
        out: Dict[str, Any] = {"what": "fees = claimed + unclaimed; a claim moves exactly the unclaimed amount"}
        out["cleanup_before_claim"] = self.cleanup()
        time.sleep(2)
        s_pre = self.net.stats(self.B)
        rows = [fill_row(f, self.B, None, self.T) for f in self.builder_fills_since(self.start_height)]
        tot = sum(r["builder_fee_charged_6dec"] or 0 for r in rows)
        out["run_fills_naming_builder"] = [{k: r[k] for k in ("fill_id", "height", "builder_fee_charged_6dec")} for r in rows]
        out["builder_stats_at_start"] = s_start
        out["builder_stats_before_claim"] = s_pre
        d_fees = int(s_pre["fees_6dec"]) - int(s_start["fees_6dec"])
        d_unc = int(s_pre["unclaimed_6dec"]) - int(s_start["unclaimed_6dec"])
        d_cl = int(s_pre["claimed_6dec"]) - int(s_start["claimed_6dec"])
        out["before_claim"] = {"sum_run_fill_fees_6dec": tot, "fees_delta_6dec": d_fees, "unclaimed_delta_6dec": d_unc,
                               "claimed_delta_6dec": d_cl, "sum_equals_claimed_plus_unclaimed_delta": tot == d_unc + d_cl,
                               "identity_fees_eq_unclaimed_plus_claimed": int(s_pre["fees_6dec"]) == int(s_pre["unclaimed_6dec"]) + int(s_pre["claimed_6dec"])}
        bal0, res0 = self.net.balance(self.B), self.net.get("/reserves/identity")
        r = self.bops.claim_builder_fees()
        time.sleep(1.5)
        s_post, bal1, res1 = self.net.stats(self.B), self.net.balance(self.B), self.net.get("/reserves/identity")
        out["claim"] = {"applied": r.applied, "http_status": r.status_code, "answer": r.answer, "detail": r.detail,
                        "head_after": self.net.head()}
        out["builder_stats_after_claim"] = s_post
        out["builder_balance_before_after"] = [bal0, bal1]
        pick = lambda j: {"unclaimed_builder_fees_6dec": ((j.get("buckets") or {}).get("unclaimed_builder_fees_6dec")),
                          "identity_holds": (j.get("identity") or {}).get("holds"),
                          "height": (j.get("as_of") or {}).get("height")} if isinstance(j, dict) else j
        out["reserves_identity_builder_bucket_before_after"] = [pick(res0), pick(res1)]
        unc = int(s_pre["unclaimed_6dec"])
        out["after_claim"] = {
            "unclaimed_before_6dec": unc,
            "claimed_rise_6dec": int(s_post["claimed_6dec"]) - int(s_pre["claimed_6dec"]),
            "claimed_rose_by_exactly_unclaimed": int(s_post["claimed_6dec"]) - int(s_pre["claimed_6dec"]) == unc,
            "unclaimed_after_6dec": int(s_post["unclaimed_6dec"]),
            "fees_unchanged_by_claim": s_post["fees_6dec"] == s_pre["fees_6dec"],
            "identity_fees_eq_unclaimed_plus_claimed": int(s_post["fees_6dec"]) == int(s_post["unclaimed_6dec"]) + int(s_post["claimed_6dec"]),
            "builder_balance_rise_6dec": int(bal1.get("total") or 0) - int(bal0.get("total") or 0),
            "balance_rose_by_exactly_unclaimed": int(bal1.get("total") or 0) - int(bal0.get("total") or 0) == unc}
        ok = out["before_claim"]["sum_equals_claimed_plus_unclaimed_delta"] and all(
            out["after_claim"][k] for k in ("claimed_rose_by_exactly_unclaimed", "fees_unchanged_by_claim",
                                            "identity_fees_eq_unclaimed_plus_claimed")) and out["after_claim"]["unclaimed_after_6dec"] == 0
        out["status"] = "as_expected" if ok else "unexpected"
        log(f"f: run fills {len(rows)} sum {tot}; fees moved {d_fees} (unclaimed {d_unc} + claimed {d_cl}); claim "
            f"applied {r.applied}; claimed rose {out['after_claim']['claimed_rise_6dec']} of {unc}; balance rose "
            f"{out['after_claim']['builder_balance_rise_6dec']} -> {out['status']}")
        self.case("f_claim_reconciliation", out)

    def final(self):
        out = self.cleanup()
        appr = self.net.approvals(self.T)
        out["revokes"] = [self.approve(a["builder"], 0) for a in appr.get("approvals") or []]
        out["approvals_after"] = self.net.approvals(self.T)
        out["trader_balance_after"] = self.net.balance(self.T)
        out["builder_balance_after"] = self.net.balance(self.B)
        self.case("z_cleanup", out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--make-keys", metavar="DIR", help="make a fresh trader key and builder key (mode 600) in DIR and stop")
    ap.add_argument("--trader-key-file", help="the trader's key (mode 600)")
    ap.add_argument("--builder-key-file", help="the builder's key (mode 600)")
    ap.add_argument("--filler-key-dir", help="folder for the extra builder keys of case d (made when missing; they hold no funds)")
    ap.add_argument("--out", help="folder for results.json and console.log (default ./proof-<UTC time>)")
    ap.add_argument("--live", action="store_true", help="send on the test network")
    ap.add_argument("--market", default="ETH")
    ap.add_argument("--leverage", type=int, default=2)
    ap.add_argument("--fee-a", type=int, default=500, help="builder fee for case a, cbps (default 500)")
    ap.add_argument("--fee-c", type=int, default=300, help="approved rate for case c, cbps (default 300)")
    ap.add_argument("--fee-e", type=int, default=400, help="builder fee for case e, cbps (default 400)")
    ap.add_argument("--min-usdc", type=int, default=50, help="test USDC each account must have available (default 50)")
    ap.add_argument("--only", help="comma list of cases to run (a,b,c,d,e,f); default all")
    a = ap.parse_args(argv)
    if a.make_keys:
        make_keys(a.make_keys)
        return 0
    if not (a.trader_key_file and a.builder_key_file):
        ap.error("--trader-key-file and --builder-key-file are required (or --make-keys DIR)")
    cases = set((a.only or "a,b,c,d,e,f").split(","))
    if "d" in cases and not a.filler_key_dir:
        ap.error("case d needs --filler-key-dir")
    out = Path(a.out or f"proof-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}").resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty: give a fresh --out")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["VORDIUM_STATE_DIR"] = str(out / "nonces")         # client-nonce marks stay with this run
    os.environ["VORDIUM_NETWORK"] = "testnet"
    log = Log(out / "console.log")
    p = Proof(a, log, out)
    log(f"builder-fee proof, {'LIVE on the test network' if a.live else 'CHECK ONLY (nothing signed or sent)'}; record in {out}")
    rc = 0
    started = False
    try:
        if not p.preflight():
            return 3
        if not a.live:
            log("check only: both accounts are ready. Run again with --live to send.")
            return 0
        started = True
        p.start_height = p.net.head() or 0
        s_start = p.net.stats(p.B)
        for k, fn in (("a", p.case_a), ("b", p.case_b), ("c", p.case_c), ("d", p.case_d), ("e", p.case_e)):
            if k in cases:
                try:
                    fn()
                except Exception as e:
                    log(f"ERROR in case {k}:", f"{type(e).__name__}: {e}")
                    p.case(f"{k}_error", {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]})
                    rc = 1
        if "f" in cases:
            p.case_f(s_start)
    except SystemExit:
        raise
    except Exception as e:
        log("ERROR:", f"{type(e).__name__}: {e}")
        p.res["error"] = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]}
        rc = 1
    finally:
        if started:
            try:
                p.final()
            except Exception as e:
                log("cleanup failed:", f"{type(e).__name__}: {e}")
        p.res["finished"] = iso()
        p.res["summary"] = {k: v.get("status") for k, v in p.res["cases"].items() if isinstance(v, dict) and "status" in v}
        p.save()
        log("summary:", json.dumps(p.res["summary"]))
    log("record:", out / "results.json")
    return rc


if __name__ == "__main__":
    sys.exit(main())
