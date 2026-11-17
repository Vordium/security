"""Shared helpers for the agent-control checks (Vordium test network only).

Every check is one file that imports this module. A check:
  * refuses any network other than the Vordium test network (chain id 101102), before anything is signed;
  * makes its own throwaway keys (written mode 600 into --keys-dir, never printed);
  * prints one JSON line per step and a verdict line;
  * exits 0 when the defence holds, 1 when the attack works, 3 when it cannot run.

Public tools only: the Vordium Python SDK (``vordium`` on PyPI), ``eth-account`` and ``requests``.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

TESTNET_CHAIN_ID = 101102
SPEC_URL = "https://testnet.vordex.xyz/network-spec.json"
REST = "https://testnet.vordex.xyz/chain"
UA = {"User-Agent": "vordium-shield-check/1", "Accept": "application/json", "Cache-Control": "no-store"}
E6, E8, E18 = 10 ** 6, 10 ** 8, 10 ** 18

HOLDS, WORKS, CANNOT = 0, 1, 3
LINE_MAX = 4000             # the longest step line printed


def now_ms() -> int:
    return int(time.time() * 1000)


# -- output -------------------------------------------------------------------------------------------------------------
class Run:
    """One check: its steps, its verdict, its exit code."""

    def __init__(self, vector: str, title: str, argv=None, extra: Optional[Callable[[argparse.ArgumentParser], None]] = None):
        p = argparse.ArgumentParser(description=f"{vector}: {title}")
        p.add_argument("--keys-dir", default=os.environ.get("SHIELD_KEYS_DIR", "keys"),
                       help="where throwaway keys are written (mode 700 folder, 600 files)")
        p.add_argument("--out", default=None, help="write the record as JSON to this file")
        p.add_argument("--owner-key-file", default=os.environ.get("SHIELD_OWNER_KEY_FILE"),
                       help="a FUNDED test-network owner key (mode 600), for checks that need a balance")
        if extra:
            extra(p)
        self.args = p.parse_args(argv)
        self.vector, self.title = vector, title
        self.steps: List[Dict[str, Any]] = []
        self.started = now_ms()

    def step(self, _step: str, **data: Any) -> Dict[str, Any]:
        row = {"step": _step, "at_ms": now_ms(), **data}
        self.steps.append(row)
        print(json.dumps(row, default=str)[:LINE_MAX], flush=True)
        return row

    def end(self, code: int, verdict: str) -> None:
        word = {HOLDS: "DEFENCE HOLDS", WORKS: "ATTACK WORKS", CANNOT: "CANNOT RUN"}[code]
        rec = {"vector": self.vector, "title": self.title, "result": word, "exit": code, "verdict": verdict,
               "started_ms": self.started, "ended_ms": now_ms(), "steps": self.steps}
        if self.args.out:
            Path(self.args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(self.args.out).write_text(json.dumps(rec, indent=1, default=str))
        print(f"RESULT {self.vector} {word}: {verdict}", flush=True)
        sys.exit(code)


# -- keys ---------------------------------------------------------------------------------------------------------------
def new_key(run: Run, label: str) -> str:
    """A fresh throwaway key, written mode 600 under --keys-dir (folder mode 700). Only its address is ever shown."""
    from eth_account import Account
    d = Path(run.args.keys_dir)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    k = "0x" + secrets.token_hex(32)
    path = d / f"{run.vector}-{label}-{now_ms()}.key"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(k)
    run.step("key", label=label, address=Account.from_key(k).address)
    return k


def read_key_file(path: str) -> str:
    p = Path(path).expanduser()
    st = p.stat()
    if st.st_mode & 0o077:
        raise SystemExit(f"{p} can be read by other users; chmod 600 it first")
    raw = p.read_text().strip()
    return raw if raw.startswith("0x") else "0x" + raw


def addr(key: str) -> str:
    from eth_account import Account
    return Account.from_key(key).address


# -- the network --------------------------------------------------------------------------------------------------------
def get(path: str, timeout: float = 15) -> Any:
    r = requests.get(REST + path, headers=UA, timeout=timeout)
    try:
        return r.json()
    except ValueError:
        return {"_status": r.status_code, "_text": r.text[:300]}


def post(path: str, body: Any, timeout: float = 15) -> Dict[str, Any]:
    try:
        r = requests.post(REST + path, json=body, headers=UA, timeout=timeout)
        try:
            ans = r.json()
        except ValueError:
            ans = {"_text": r.text[:300]}
        return {"http": r.status_code, "answer": ans}
    except requests.RequestException as e:
        return {"http": None, "answer": {"_error": f"{type(e).__name__}"}}


def head() -> Optional[int]:
    try:
        return int(get("/status", 8).get("chain_head"))
    except Exception:
        return None


def wait_until(pred: Callable[[], Any], secs: float = 25.0, step: float = 1.0) -> Any:
    end = time.time() + secs
    while True:
        try:
            v = pred()
            if v:
                return v
        except Exception:
            pass
        if time.time() >= end:
            return None
        time.sleep(step)


class Net:
    """The test network, checked: spec, SDK network, signing phase."""

    def __init__(self, run: Run):
        from vordium.network import use_network
        spec = requests.get(SPEC_URL, headers=UA, timeout=15).json()
        if spec.get("testnet") is not True or int(spec.get("chainId", 0)) != TESTNET_CHAIN_ID:
            run.step("refused", why="the spec does not describe the Vordium test network (chain 101102)")
            run.end(CANNOT, "not the test network; nothing was signed")
        net = use_network("testnet")
        if net.chain_id != TESTNET_CHAIN_ID:
            run.end(CANNOT, "the SDK resolved another network; nothing was signed")
        from vordium.rollb import read_signing_phase
        self.spec = spec
        self.net = net
        self.phase = read_signing_phase()
        self.pairs = {p["symbol"]: p for p in spec["markets"]["pairs"]}
        st = get("/status")
        run.step("network", chain_id=net.chain_id, head=st.get("chain_head"), binary=st.get("binary_sha8"),
                 phase=getattr(self.phase, "kind", None), trading_open=st.get("trading_open"))
        if getattr(self.phase, "kind", None) != "genesis-bound":
            run.end(CANNOT, f"named agents are not in force at this height (signing phase {self.phase.kind})")

    def pair(self, base: str) -> Dict[str, Any]:
        for k in (base.upper() + "USDT", base.upper() + "USD", base.upper()):
            if k in self.pairs:
                return self.pairs[k]
        raise SystemExit(f"no market {base} on the test network")

    def oracle8(self, pair_id: int) -> int:
        return int(get(f"/oracle/{pair_id}")["oracle_price"]) * 100

    def px(self, pair: Dict[str, Any], frac: str, rounding=ROUND_FLOOR) -> int:
        tick = int(pair["tick8dec"])
        return int((Decimal(self.oracle8(pair["pairId"])) * Decimal(frac) / tick).to_integral_value(rounding) * tick)

    def size18(self, pair: Dict[str, Any], usd: str, price8: int) -> int:
        lot = int(pair["lot18dec"])
        return int((Decimal(usd) * E8 * E18 / Decimal(price8) / lot).to_integral_value(ROUND_CEILING) * lot)


# -- operations by the owner (any key may SIGN them; only the owner's are meant to apply) ---------------------------------------
class Nonce:
    def __init__(self):
        self.last = 0

    def __call__(self) -> int:
        self.last = max(now_ms(), self.last + 1)
        return self.last


NONCE = Nonce()


def signed_op(signing_key: str, op: str, value: Dict[str, Any]) -> Dict[str, Any]:
    from vordium.agent_ops import sign_owner_op
    return sign_owner_op(signing_key, op, value)


def submit(body: Dict[str, Any]) -> Dict[str, Any]:
    return post("/submit", body)


def agent_rec(owner: str, agent: str) -> Dict[str, Any]:
    j = get(f"/agents/{owner.lower()}/{agent.lower()}")
    return j if isinstance(j, dict) else {}


def rec_of(j: Dict[str, Any]) -> Dict[str, Any]:
    return j.get("agent") if isinstance(j.get("agent"), dict) else j


def policy_of(j: Dict[str, Any]) -> Dict[str, Any]:
    r = rec_of(j)
    for k in ("policy_v1", "policy"):
        if isinstance(r.get(k), dict):
            return r[k]
    return {}


def market_rows(j: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = rec_of(j)
    return list(r.get("market_limits") or j.get("market_limits") or [])


def is_live(j: Dict[str, Any]) -> bool:
    r = rec_of(j)
    if j.get("found") is False or not r:
        return False
    if r.get("revoked") is True or "revok" in str(r.get("status", "")).lower():
        return False
    exp = r.get("expires_ms")
    return not (isinstance(exp, int) and 0 < exp <= now_ms())


def default_policy(exp_ms: int, **over: Any):
    from vordium.policy import PolicyV1
    base = dict(caps_bitmask=0b010011, side_mode=0, max_total_exposure_6dec=200 * E6, max_leverage_bps=5 * 10000,
                daily_loss_limit_6dec=5 * E6, daily_fee_cap_6dec=0, ops_per_window=0, ops_window_ms=0,
                active_from_ms_of_day=0, active_to_ms_of_day=0, oracle_band_bps=1000, lock_auto_clear=False,
                expires_ms=exp_ms, enabled=True)
    base.update(over)
    return PolicyV1(**base)


def setup_agent(run: Run, net: Net, owner_key: str, agent_key: str, name: str, allowed_pair: Optional[Dict[str, Any]] = None,
                max_order18: int = 0, hours: float = 1.0, policy=None, need_policy: bool = True) -> Dict[str, Any]:
    """Register the agent, set its policy and one allowed market, each read back from the chain."""
    from vordium.agent_ops import registration, set_policy
    owner, agent = addr(owner_key), addr(agent_key)
    exp = now_ms() + int(hours * 3600_000)
    op, val = registration(owner, agent, "shield check (test network)", exp, NONCE(), net.phase, name=name)
    r = submit(signed_op(owner_key, op, val))
    ok = wait_until(lambda: is_live(agent_rec(owner, agent)))
    run.step("setup_register", owner=owner, agent=agent, name=name, http=r["http"], answer=r["answer"], applied=bool(ok))
    if not ok:
        run.end(CANNOT, "the agent could not be registered: " + json.dumps(r["answer"])[:200])
    if not need_policy:
        return {"owner": owner, "agent": agent, "exp": exp}
    pol = policy or default_policy(exp)
    op, val = set_policy(owner, agent, pol, NONCE(), net.phase, now_ms())
    r = submit(signed_op(owner_key, op, val))
    ok = wait_until(lambda: policy_of(agent_rec(owner, agent)).get("enabled") is pol.enabled
                    and int(policy_of(agent_rec(owner, agent)).get("expires_ms") or 0) == pol.expires_ms)
    run.step("setup_policy", http=r["http"], answer=r["answer"], applied=bool(ok))
    if not ok:
        run.end(CANNOT, "the policy did not apply: " + json.dumps(r["answer"])[:200])
    if allowed_pair is not None:
        mo = max_order18 or int(allowed_pair["lot18dec"]) * 1000
        r = submit(signed_op(owner_key, "SetAgentMarketLimit", {
            "owner": owner, "agent": agent, "pair": int(allowed_pair["pairId"]), "allowed": True,
            "maxOrder18dec": mo, "maxPosition18dec": mo * 3, "maxLeverageBps": 5 * 10000, "nonce": NONCE()}))
        ok = wait_until(lambda: any(int(m.get("pair", -1)) == int(allowed_pair["pairId"]) and m.get("allowed")
                                    for m in market_rows(agent_rec(owner, agent))))
        run.step("setup_market_limit", pair=allowed_pair["symbol"], max_order18=mo, http=r["http"], answer=r["answer"],
                 applied=bool(ok))
        if not ok:
            run.end(CANNOT, "the market limit did not apply")
    return {"owner": owner, "agent": agent, "exp": exp}


# -- orders signed by any key --------------------------------------------------------------------------------------------
SENT_NONCES: set = set()          # every client nonce this check signed: clean-up touches only these orders


def order_body(signing_key: str, owner: str, pair_id: int, side: int, size18: int, price8: int, leverage_bps: int = 10000,
               order_type: int = 1, reduce_only: bool = False, client_nonce: Optional[int] = None) -> Dict[str, Any]:
    from vordium import dex as D, nonces
    from vordium.caps import place_order_struct_hash
    n = client_nonce if client_nonce is not None else nonces.next_nonce(owner, nonces.ORDERS)
    SENT_NONCES.add(str(n))
    dx = D.Vordex()
    sig = D._sign_digest(signing_key, dx._digest(place_order_struct_hash(owner, pair_id, side, size18, price8, leverage_bps,
                                                                         order_type, reduce_only, n, False, 0, 0)))
    return D.place_order_body(owner, addr(signing_key), pair_id, side, size18, price8, leverage_bps, order_type,
                              reduce_only, False, 0, 0, n, sig)


def cancel_body(signing_key: str, owner: str, order_id: int) -> Dict[str, Any]:
    from vordium import dex as D
    from vordium.caps import cancel_order_struct_hash
    dx = D.Vordex()
    sig = D._sign_digest(signing_key, dx._digest(cancel_order_struct_hash(owner, order_id)))
    return D.cancel_order_body(owner, addr(signing_key), order_id, sig)


def orders_of(owner: str) -> List[Dict[str, Any]]:
    j = get(f"/orders/{owner}")
    rows = j if isinstance(j, list) else (j.get("orders") or [] if isinstance(j, dict) else [])
    return [o for o in rows if isinstance(o, dict)]


def agent_events(agent: str, limit: int = 100) -> List[Dict[str, Any]]:
    j = get(f"/events/agent/{agent.lower()}?limit={limit}")
    return [e for e in (j.get("events") if isinstance(j, dict) else None) or [] if isinstance(e, dict)]


def account_events(owner: str, limit: int = 100) -> List[Dict[str, Any]]:
    j = get(f"/events/account/{owner.lower()}?limit={limit}")
    return [e for e in (j.get("events") if isinstance(j, dict) else None) or [] if isinstance(e, dict)]


def order_fate(owner: str, agent: str, nonce: int, intake: Dict[str, Any], wait_s: float = 10.0) -> Dict[str, Any]:
    """What became of one order, by its client nonce: refused at intake, refused after receipt, resting, or no record."""
    ans = intake.get("answer") if isinstance(intake.get("answer"), dict) else {}
    if intake.get("http") is not None and intake["http"] >= 400:
        return {"outcome": "refused_at_intake", "http": intake["http"], "code": ans.get("code"),
                "reason": ans.get("reason") or ans.get("error")}
    want = str(nonce)
    end = time.time() + wait_s
    while True:
        for e in agent_events(agent):
            if e.get("kind") == "agent_refused" and str(e.get("client_nonce")) == want:
                return {"outcome": "refused_after_receipt", "code": "agent_refused", "reason": e.get("reason"),
                        "height": e.get("height")}
        for o in orders_of(owner):
            if str(o.get("client_nonce")) == want:
                return {"outcome": "accepted_resting", "order_id": o.get("id", o.get("order_id")), "order": o}
        evs = [e for e in account_events(owner) if str(e.get("client_nonce")) == want]
        if evs:
            bad = [e for e in evs if "refus" in str(e.get("kind", "")).lower() or "reject" in str(e.get("kind", "")).lower()]
            if bad:
                return {"outcome": "refused_after_receipt", "code": bad[0].get("code"), "reason": bad[0].get("reason"),
                        "kind": bad[0].get("kind")}
            oid = next((e.get("order_id") for e in evs if e.get("order_id") is not None), None)
            return {"outcome": "accepted_recorded", "order_id": oid, "events": evs[:3]}
        if time.time() >= end:
            return {"outcome": "no_record", "http": intake.get("http"), "answer": ans}
        time.sleep(0.7)


def owner_cancel_all_resting(run: Run, owner_key: str) -> None:
    """Clean-up: the owner cancels the orders THIS check placed that still rest (matched by the client nonces it signed;
    any other order of the account is left alone)."""
    owner = addr(owner_key)
    for o in orders_of(owner):
        oid = o.get("id", o.get("order_id"))
        if oid is not None and str(o.get("client_nonce")) in SENT_NONCES:
            r = post("/order/cancel", cancel_body(owner_key, owner, int(oid)))
            run.step("cleanup_cancel", order_id=oid, http=r["http"])


# -- other signed operations an attacker may try with an agent key -------------------------------------------------------
def separator(domain_class: str) -> bytes:
    """The genesis-bound EIP-712 domain separator of the test network (VordCore or VordexSession), from the SDK's pin."""
    from vordium import domains
    from vordium.network import get_network, signing_pin
    pin = signing_pin(get_network())
    return domains.separator(domain_class, pin.chain_id, pin.genesis_sha256)


def typed_sign(signing_key: str, domain_class: str, name: str, fields, value: Dict[str, Any]) -> str:
    from vordium.account_ops import digest, sign_digest
    return sign_digest(signing_key, digest(separator(domain_class), name, fields, value))


def setup_or_end(run: Run, net: Net, label: str = "", **kw) -> Dict[str, Any]:
    """A fresh owner and agent: registered, with the default policy and ETH as the one allowed market."""
    ok_, ak = new_key(run, "owner" + label), new_key(run, "agent" + label)
    eth = net.pair("ETH")
    s = setup_agent(run, net, ok_, ak, kw.pop("name", "shield check"), allowed_pair=eth, **kw)
    s.update(owner_key=ok_, agent_key=ak, eth=eth)
    return s


VOLATILE = {"as_of", "head_height", "batch_height", "read_at", "chain_time_ms", "computed_at", "now_ms", "head",
            "generated_at", "at_ms"}


def stable(v: Any) -> Any:
    """A read without the fields that change on every read (the height it was read at, the time)."""
    if isinstance(v, dict):
        return {k: stable(x) for k, x in v.items() if k not in VOLATILE}
    if isinstance(v, list):
        return [stable(x) for x in v]
    return v


def unchanged(run: Run, label: str, read: Callable[[], Any], before: Any, wait_s: float = 12.0) -> bool:
    """Read the chain for ``wait_s``; True when the value never moved from ``before`` (read-time fields ignored)."""
    end = time.time() + wait_s
    raw_read = read
    read = lambda: stable(raw_read())
    before = stable(before)
    last = before
    while time.time() < end:
        try:
            last = read()
        except Exception:
            pass
        if last != before:
            run.step(label + "_changed", before=before, after=last)
            return False
        time.sleep(1.5)
    run.step(label + "_unchanged", value=last)
    return True


def intake_refused(r: Dict[str, Any]) -> bool:
    return r.get("http") is not None and r["http"] >= 400


def require_funded(run: Run) -> str:
    if not run.args.owner_key_file:
        run.end(CANNOT, "this check needs a funded test-network owner: pass --owner-key-file (claim test USDC at "
                        "https://testnet.vordex.xyz/faucet first)")
    k = read_key_file(run.args.owner_key_file)
    bal = get(f"/balance/{addr(k)}")
    avail = int((bal or {}).get("available") or 0)
    run.step("funded_owner", owner=addr(k), available_6dec=avail)
    if avail < 30 * E6:
        run.end(CANNOT, "the owner has less than 30 test USDC available")
    return k


def expect_refusal(run: Run, s: Dict[str, Any], body: Dict[str, Any], reasons, what: str) -> None:
    """Send one agent-signed order; DEFENCE HOLDS when the chain refuses it with one of ``reasons``; ATTACK WORKS when
    it rests or is recorded; any other refusal = CANNOT RUN (it says nothing about this limit)."""
    reasons = (reasons,) if isinstance(reasons, str) else tuple(reasons)
    r = post("/order/place", body)
    fate = order_fate(s["owner"], s["agent"], body["clientNonce"], r, 10)
    run.step("attack", what=what, http=r["http"], answer=r["answer"], fate=fate)
    if fate["outcome"].startswith("accepted"):
        owner_cancel_all_resting(run, s["owner_key"])
        run.end(WORKS, f"{what}: the chain took the order ({fate['outcome']})")
    if fate["outcome"].startswith("refused") and (fate.get("reason") in reasons or fate.get("code") in reasons):
        run.end(HOLDS, f"{what}: refused with {fate.get('reason') or fate.get('code')}")
    run.end(CANNOT, f"{what}: refused for another reason ({fate.get('code')}/{fate.get('reason')}), so this limit was not reached")


def near(net: Net, pair: Dict[str, Any], side: int = 0) -> int:
    """A limit price inside the policy band but away from the book: 3 % below the oracle for a buy, above for a sell."""
    return net.px(pair, "0.97" if side == 0 else "1.03", ROUND_FLOOR if side == 0 else ROUND_CEILING)


def funded_setup(run: Run, net: Net, policy_over: Optional[Dict[str, Any]] = None, key_attr: str = "agent_key_file",
                  name: str = "shield funded check") -> Dict[str, Any]:
    """The funded owner and ONE agent for it. With --agent-key-file the same agent is reused across checks (an account
    has few agent places); it is registered here when it is not live yet (30 minutes, ETH allowed, default policy)."""
    ok_ = require_funded(run)
    owner = addr(ok_)
    eth = net.pair(os.environ.get("SHIELD_FUNDED_MARKET", "ETH"))      # the one market the funded checks trade
    ak = None
    if getattr(run.args, key_attr, None):
        p = Path(getattr(run.args, key_attr))
        if p.exists():
            ak = read_key_file(str(p))
        else:
            p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            ak = "0x" + secrets.token_hex(32)
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(ak)
    else:
        ak = new_key(run, "agent")
    agent = addr(ak)
    rec = agent_rec(owner, agent)
    if is_live(rec) and any(int(m.get("pair", -1)) == int(eth["pairId"]) and m.get("allowed") for m in market_rows(rec)) \
            and policy_of(rec).get("enabled") is True:
        run.step("agent_reused", owner=owner, agent=agent)
        s = {"owner": owner, "agent": agent, "exp": rec_of(rec).get("expires_ms")}
    else:
        sg = get(f"/signers/{owner}") or {}
        lim = (sg.get("agent_limit") or {}) if isinstance(sg, dict) else {}
        run.step("agent_places", used=lim.get("agents_used"), limit=lim.get("agent_limit"))
        if isinstance(lim.get("agents_used"), int) and isinstance(lim.get("agent_limit"), int) \
                and lim["agent_limit"] - lim["agents_used"] < 2:
            run.end(CANNOT, "the funded owner has fewer than two free agent places; try again later")
        exp = now_ms() + 1800_000
        s = setup_agent(run, net, ok_, ak, f"{name} {now_ms() % 1000000}", allowed_pair=eth, hours=0.5,   # names are unique per owner
                        policy=default_policy(exp, **(policy_over or {})) if policy_over else None)
    s.update(owner_key=ok_, agent_key=ak, eth=eth)
    return s


def funded_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--agent-key-file", default=os.environ.get("SHIELD_AGENT_KEY_FILE"),
                   help="reuse this agent of the funded owner across checks (made and registered when missing)")
    p.add_argument("--agent2-key-file", default=os.environ.get("SHIELD_AGENT2_KEY_FILE"),
                   help="a second agent of the funded owner, with the modify and take-profit/stop-loss capabilities")


TPSL_CAPS = {"caps_bitmask": 0b011111}           # place, cancel, modify, tp/sl, close


def owner_rests(run: Run, net: Net, s: Dict[str, Any], usd: str = "15", frac: str = "0.93") -> Dict[str, Any]:
    """The owner places one small resting buy away from the book (its own key); returns the order record."""
    eth = s["eth"]
    p8 = net.px(eth, frac)
    body = order_body(s["owner_key"], s["owner"], eth["pairId"], 0, net.size18(eth, usd, p8), p8)
    r = post("/order/place", body)
    fate = order_fate(s["owner"], s["owner"], body["clientNonce"], r, 12)
    run.step("owner_order", http=r["http"], fate={k: v for k, v in fate.items() if k != "order"})
    if not fate["outcome"].startswith("accepted") or fate.get("order_id") is None:
        owner_cancel_all_resting(run, s["owner_key"])
        run.end(CANNOT, "the owner's own resting order could not be placed")
    return fate


def resting_ids(owner: str) -> List[int]:
    return sorted(int(o.get("id", o.get("order_id"))) for o in orders_of(owner) if o.get("id", o.get("order_id")) is not None)


# -- positions, take-profit / stop-loss, stop orders -------------------------------------------------------------------
def rows_of(j: Any, key: str) -> List[Dict[str, Any]]:
    rows = j if isinstance(j, list) else (j.get(key) if isinstance(j, dict) else None)
    return [r for r in rows or [] if isinstance(r, dict)]


def position_of(owner: str, pair_id: int) -> Optional[Dict[str, Any]]:
    for p in rows_of(get(f"/positions/{owner}"), "positions"):
        if p.get("pair_id") == pair_id and int(str(p.get("size", p.get("size_18dec", 0))) or 0) != 0:
            return p
    return None


def pos_size18(p: Optional[Dict[str, Any]]) -> int:
    """Signed size: + long, - short, 0 none."""
    if not p:
        return 0
    n = int(str(p.get("size", p.get("size_18dec", 0))) or 0)
    return n if p.get("is_long", True) else -abs(n)


def tpsl_of(owner: str, position_id: Any) -> Dict[str, int]:
    r = next((x for x in rows_of(get(f"/tpsl/{owner}"), "orders") if str(x.get("position_id")) == str(position_id)), {})
    return {"take_profit": int(r.get("take_profit") or 0), "stop_loss": int(r.get("stop_loss") or 0)}


def tpsl_body(signing_key: str, owner: str, pair_id: int, position_id: int, tp8: int, sl8: int) -> Dict[str, Any]:
    from vordium import dex as D
    from vordium.caps import set_tpsl_struct_hash
    sig = D._sign_digest(signing_key, D.Vordex()._digest(set_tpsl_struct_hash(owner, pair_id, position_id, tp8, sl8)))
    return D.set_tpsl_body(owner, addr(signing_key), pair_id, position_id, tp8, sl8, sig)


def stop_body(signing_key: str, owner: str, pair_id: int, side: int, size18: int, trigger8: int, trigger_dir: int,
              order_type: int = 2, price8: int = 0, reduce_only: bool = False, client_nonce: Optional[int] = None,
              leverage_bps: int = 10000) -> Dict[str, Any]:
    """A signed stop order (2 stop-market, 3 stop-limit). The SDK refuses to build these; the network takes them."""
    from vordium import dex as D, nonces
    from vordium.caps import place_order_struct_hash
    n = client_nonce if client_nonce is not None else nonces.next_nonce(owner, nonces.ORDERS)
    SENT_NONCES.add(str(n))
    sig = D._sign_digest(signing_key, D.Vordex()._digest(place_order_struct_hash(
        owner, pair_id, side, size18, price8, leverage_bps, order_type, reduce_only, n, False, trigger8, trigger_dir)))
    body = {"owner": owner, "pairId": int(pair_id), "side": "buy" if side == 0 else "sell", "size_18dec": str(size18),
            "orderType": {2: "StopMarket", 3: "StopLimit"}[order_type], "reduceOnly": bool(reduce_only),
            "leverageBps": int(leverage_bps), "clientNonce": n, "sessionKey": addr(signing_key), "post_only": False,
            "trigger_price_8dec": int(trigger8), "trigger_dir": int(trigger_dir), "signature": sig}
    if order_type == 3:
        body["price"] = float(Decimal(price8) / E8)
    return body


def dormant_stop(net: "Net", signing_key: str, owner: str, pair: Dict[str, Any], usd: str = "30") -> Dict[str, Any]:
    """A buy stop-market that fires only if the mark falls to half the price: it rests and never fills. Sized so that
    its value at the trigger is above the minimum order."""
    tick = int(pair["tick8dec"])
    o8 = net.oracle8(pair["pairId"])
    trig = (o8 // 2) // tick * tick
    return stop_body(signing_key, owner, pair["pairId"], 0, net.size18(pair, usd, o8), trig, 1)


def nonce_resting(owner: str, nonce: Any) -> List[Dict[str, Any]]:
    return [o for o in orders_of(owner) if str(o.get("client_nonce")) == str(nonce)]


def owner_market(run: Run, net: "Net", s: Dict[str, Any], side: int, size18: int, reduce_only: bool = False) -> Dict[str, Any]:
    """The owner's own market order (to open or close a small position)."""
    b = order_body(s["owner_key"], s["owner"], s["eth"]["pairId"], side, size18, 0, order_type=0, reduce_only=reduce_only)
    r = post("/order/place", b)
    run.step("owner_market", side=side, size18=size18, reduce_only=reduce_only, http=r["http"], answer=r["answer"])
    return r


def close_position(run: Run, net: "Net", s: Dict[str, Any]) -> None:
    p = position_of(s["owner"], s["eth"]["pairId"])
    n = pos_size18(p)
    if n:
        owner_market(run, net, s, 1 if n > 0 else 0, abs(n), reduce_only=True)
        wait_until(lambda: pos_size18(position_of(s["owner"], s["eth"]["pairId"])) == 0, 20)
    run.step("cleanup_position", left=pos_size18(position_of(s["owner"], s["eth"]["pairId"])))


def open_long(run: Run, net: "Net", s: Dict[str, Any], lots: int = 100) -> Dict[str, Any]:
    """The owner opens a small long (default 100 lots: 0.01 ETH on the test network) and returns the position."""
    if position_of(s["owner"], s["eth"]["pairId"]):
        run.end(CANNOT, "the funded owner already holds an ETH position; this check needs a flat account")
    owner_market(run, net, s, 0, int(s["eth"]["lot18dec"]) * lots)
    p = wait_until(lambda: position_of(s["owner"], s["eth"]["pairId"]), 25)
    run.step("position", position=p)
    if not p:
        run.end(CANNOT, "the owner's market order did not open a position (book empty?)")
    return p


def twap_body(net: "Net", signing_key: str, owner: str, pair: Dict[str, Any], usd: str = "150", slices: int = 10,
              trigger_frac: Optional[str] = "0.5", leverage_bps: int = 10000, total18: Optional[int] = None) -> Dict[str, Any]:
    """A signed PlaceTwap (VordCore domain). With a trigger at half the price it waits and never runs a slice."""
    from vordium import account_ops as AO
    o8 = net.oracle8(pair["pairId"])
    lot, tick = int(pair["lot18dec"]), int(pair["tick8dec"])
    total = total18 if total18 is not None else max(net.size18(pair, usd, o8) // (lot * slices), 1) * lot * slices
    trig = (int(Decimal(o8) * Decimal(trigger_frac)) // tick * tick) if trigger_frac else 0
    cn = now_ms()
    SENT_NONCES.add(str(cn))
    v = {"owner": owner, "pairId": pair["pairId"], "side": 0, "totalSize18dec": total, "numSlices": slices,
         "durationMs": 3600_000, "leverageBps": leverage_bps, "slippageBps": 100, "randomize": False,
         "triggerPrice8dec": trig, "triggerDir": 1 if trig else 0, "minPrice8dec": 0, "maxPrice8dec": 0, "clientNonce": cn}
    sig = typed_sign(signing_key, "VordCore", "PlaceTwap", AO.PLACE_TWAP, v)
    return json.loads(AO.twap_body(v, sig))


def twaps_of(owner: str) -> List[Dict[str, Any]]:
    return rows_of(get(f"/twaps/{owner.lower()}"), "twaps")


def twap_running(owner: str, nonce: Any) -> List[Dict[str, Any]]:
    return [t for t in twaps_of(owner) if str(t.get("client_nonce")) == str(nonce)
            and str(t.get("status", "running")).lower() not in ("ended", "cancelled", "canceled", "done", "finished")]


def agent_reason(answer: Any) -> Optional[str]:
    """The agent refusal in an answer: its reason, or the code agent_refused; None when the refusal is about something else."""
    if not isinstance(answer, dict):
        return None
    if answer.get("code") == "agent_refused" or answer.get("reason"):
        return answer.get("reason") or "agent_refused"
    return None


def stop_all_signers(owner_key: str) -> Dict[str, Any]:
    FIELDS = [("owner", "address"), ("nonce", "uint256"), ("validUntil", "uint256")]
    v = {"owner": addr(owner_key), "nonce": NONCE(), "validUntil": now_ms() // 1000 + 120}
    return post("/signers/stop-all", {**v, "signature": typed_sign(owner_key, "VordexSession", "StopAllSigners", FIELDS, v)})


def use_position(run: Run, net: "Net", s: Dict[str, Any]) -> Dict[str, Any]:
    """A position for the take-profit / stop-loss checks: the account's own ETH position when it has one (its size is
    never touched, and its take-profit / stop-loss is put back afterwards), else a small long opened here."""
    p = position_of(s["owner"], s["eth"]["pairId"])
    if p:
        pid = p.get("id", p.get("position_id"))
        s["existing_position"] = {"id": pid, "tpsl": tpsl_of(s["owner"], pid)}
        run.step("position_existing", position=p, tpsl_before=s["existing_position"]["tpsl"])
        return p
    return open_long(run, net, s)


def release_position(run: Run, net: "Net", s: Dict[str, Any]) -> None:
    ex = s.get("existing_position")
    if not ex:
        return close_position(run, net, s)
    t = dict(ex["tpsl"])
    if not t["take_profit"] and not t["stop_loss"]:
        # the network takes no "both legs off": the closest to none is a stop-loss at the lowest price step
        t["stop_loss"] = int(s["eth"]["tick8dec"])
        run.step("cleanup_note", note="the position had no take-profit/stop-loss; its stop-loss is left at the lowest price step")
    post("/tpsl/set", tpsl_body(s["owner_key"], s["owner"], s["eth"]["pairId"], int(ex["id"]), t["take_profit"], t["stop_loss"]))
    back = wait_until(lambda: tpsl_of(s["owner"], ex["id"]) == t, 25)
    run.step("cleanup_tpsl_restored", restored=bool(back), tpsl=tpsl_of(s["owner"], ex["id"]))
