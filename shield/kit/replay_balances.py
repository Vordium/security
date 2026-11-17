#!/usr/bin/env python3
"""Replay customer balances from the chain's own public records (trading-records schema revision 4).

For every balance_change record in a height window it checks, from public reads only:
  1. parts:      before/after usdc + reserved_orders + in_positions + spot_reserved = collateral (each side);
  2. delta:      delta = after.collateral - before.collateral;
  3. explained:  unexplained = delta - records_delta; explained is true exactly when unexplained is 0;
  4. legs:       the records it names, read back, move this account by records_delta in total
                 (a record's legs[] when present, else a fill's taker / maker legs, else the record's own account_delta);
  5. balance:    the last named leg that carries balance_after equals after.collateral;
  6. link:       the change it follows (since_cursor) ended at this change's `before` (a gap record's `after` is a new baseline;
                 a balance_reset starts every chain again);
  7. customers:  a customer account (system false) never has an unexplained change; a fill never pairs an account with itself.
Every change that is NOT judged is counted with its reason (system account, a leg the chain marks as not measured, a record or
link that could not be read, a gap record, a window that crosses a recorded gap). Nothing excluded is ever called a pass.

Usage:  python3 replay_balances.py --chain https://testnet.vordex.xyz/chain-archive --minutes 30 [--account 0x…] [--json out.json]
        python3 tests/test_replay.py   (the rules, with planted faults)
Exit:   0 = changes judged, no problem · 1 = a problem (listed) · 2 = could not run · 3 = nothing judged (never a pass)."""
import argparse, json, sys, time
from collections import Counter
from vordium_check.common import Reader

PARTS = ("usdc_6dec", "reserved_orders_6dec", "in_positions_6dec", "spot_reserved_6dec")
# The chain's money record kinds (GET /events/coverage money_record_kinds); the live list is used when the host serves it.
MONEY = {"fill", "funding_payment", "liquidation", "adl", "deposit_credited", "withdrawal_requested", "withdrawal_refunded",
         "evm_usdc_moved", "claim_paid", "staking_paid", "treasury_moved", "pool_deposit", "pool_withdraw", "fee_credit", "spot_fill",
         "trading_account_funded", "vault_created", "vault_deposit", "vault_withdraw", "vault_close"}


def _i(v):
    if v is None or isinstance(v, (bool, float)): raise ValueError(f"not a whole number: {v!r}")
    s = str(v)
    if not s.lstrip("-").isdigit(): raise ValueError(f"not a whole number: {s!r}")
    return int(s)


def _low(v): return v.lower() if isinstance(v, str) else None


def collateral(side):
    return sum(_i(side[k]) for k in PARTS), _i(side["collateral_6dec"])


def is_gap(e): return e.get("gap") is True


def ckey(c): return tuple(int(x) for x in str(c).split(".") if x.isdigit())


def legs_of(rec, acct):
    """[(delta, balance_after or None)] for this account in one record, and whether every one of them is measured."""
    out, measured = [], True
    def add(leg):
        nonlocal measured
        if not isinstance(leg, dict) or _low(leg.get("account")) != acct: return
        if leg.get("notes_missing") is True or leg.get("account_delta_6dec") is None: measured = False; return
        ba = leg.get("balance_after_6dec")
        out.append((_i(leg["account_delta_6dec"]), _i(ba) if ba is not None else None))
    if isinstance(rec.get("legs"), list) and rec["legs"]:
        for leg in rec["legs"]: add(leg)
    elif rec.get("kind") == "fill":
        for side in ("taker", "maker"): add(rec.get(side) or {})
    elif _low(rec.get("account")) == acct and ("account_delta_6dec" in rec or rec.get("notes_missing") is True):
        add(rec)
    return out, measured


def replay(evs, lookup, account=None, money=MONEY):
    """evs: every record in the window. lookup(cursor) -> a record outside the window, or None if unreadable.
    Returns (problems [text], counts Counter, excluded Counter{reason: n}, kinds Counter{money kind named: n})."""
    problems, n, excl, kinds = [], Counter(), Counter(), Counter()
    by = {e.get("cursor"): e for e in evs if e.get("cursor")}
    get = lambda c: by.get(c) or lookup(c)
    chains = {}
    for e in sorted(evs, key=lambda e: ckey(e.get("cursor", ""))):
        k = e.get("kind")
        if k == "fill":
            t, m = _low((e.get("taker") or {}).get("account")), _low((e.get("maker") or {}).get("account"))
            if t and t == m: problems.append(f"fill {e.get('cursor')}: taker and maker are the same account {t}")
        if k == "balance_reset":
            n["resets"] += 1
            names = [a.lower() for a in e.get("accounts") or [] if isinstance(a, str)]
            for a in names: chains.pop(a, None)
            if not names: chains.clear()
            continue
        if k != "balance_change": continue
        cur, acct = e.get("cursor"), _low(e.get("account"))
        if account and acct != account: continue
        n["changes"] += 1
        if not acct: excl["names no account"] += 1; continue
        if is_gap(e):
            excl[f"gap record ({e.get('gap_reason') or 'no reason given'}): a new baseline, not judged"] += 1
            try: chains[acct] = (cur, collateral(e["after"])[1])
            except (KeyError, TypeError, ValueError): chains.pop(acct, None)
            continue
        try:
            (bs, bc), (as_, ac) = collateral(e["before"]), collateral(e["after"])
            d, rd, ux = _i(e["delta_6dec"]), _i(e["records_delta_6dec"]), _i(e["unexplained_6dec"])
        except (KeyError, TypeError, ValueError) as x:
            excl["not in the published shape"] += 1; problems.append(f"{cur}: balance change not in the published shape ({x})")
            chains.pop(acct, None); continue
        p = []
        if bs != bc: p.append(f"before: parts {bs} != collateral {bc}")
        if as_ != ac: p.append(f"after: parts {as_} != collateral {ac}")
        if d != ac - bc: p.append(f"delta {d} != after - before {ac - bc}")
        if ux != d - rd: p.append(f"unexplained {ux} != delta - records_delta {d - rd}")
        if e.get("explained") is not (ux == 0): p.append(f"explained {e.get('explained')} while unexplained is {ux}")
        total, measured, missing, last_after, unrec, bad_leg = 0, True, [], None, False, False
        for rc in e.get("records") or []:
            r = get(rc)
            if r is None: missing.append(rc); continue
            kinds[r.get("kind") or "?"] += 1
            try: legs, m = legs_of(r, acct)
            except ValueError: bad_leg = True; continue
            if not m: measured = False; continue
            if not legs and r.get("kind") in money: unrec = True; continue   # a money record naming no leg for this account
            for dl, ba in legs:
                total += dl
                if ba is not None: last_after = ba
        system = e.get("system") is True
        if missing: excl["a named record could not be read"] += 1
        elif bad_leg: excl["a named leg is not in the published shape"] += 1; measured = False
        elif unrec: excl["a named money record carries no leg for this account (shape not recognised)"] += 1; measured = False
        elif not measured: excl["a named leg is not measured by the chain (notes_missing)"] += 1
        else:
            if total != rd: p.append(f"the named records' legs add to {total}, records_delta says {rd}")
            if last_after is not None and last_after != ac: p.append(f"the last leg's balance_after {last_after} != after {ac}")
        sc = e.get("since_cursor")
        if sc is None:
            if acct in chains: p.append(f"since_cursor is null but the account's change {chains[acct][0]} comes before it (no reset between)")
            else: n["chain starts"] += 1
        elif acct in chains and chains[acct][0] != sc:
            p.append(f"since_cursor {sc} skips the account's newest change {chains[acct][0]}")
        elif acct in chains:
            if bc != chains[acct][1]: p.append(f"before {bc} != the after {chains[acct][1]} of the change it follows ({sc})")
        else:
            prev = get(sc)
            if prev is None: excl["link: the previous change could not be read (counted, not judged)"] += 1
            elif prev.get("kind") != "balance_change" or _low(prev.get("account")) != acct:
                p.append(f"since_cursor {sc} names no balance change of this account")
            else:
                try:
                    pa = collateral(prev["after"])[1]
                    if bc != pa: p.append(f"before {bc} != the after {pa} of the change it follows ({sc})")
                except (KeyError, TypeError, ValueError): excl["link: the previous change is not in the published shape"] += 1
        if ux != 0:
            if system: n["system account, unexplained (by design, counted)"] += 1
            elif measured or unrec: p.append(f"UNEXPLAINED {ux} micro-USDC on a customer account (the chain's own figure)")
        if system: excl["system account (fee treasury, pool, vault, house): counted, not a customer"] += 1
        elif measured and not missing: n["judged"] += 1
        problems += [f"{acct} @{e.get('height')} ({cur}): {t}" for t in p]
        chains[acct] = (cur, ac)
    return problems, n, excl, kinds


SPAN = 100_000   # the records route answers at most this many heights per request


def read_window(rd, chain, lo, hi):
    evs = []
    for a in range(lo, hi + 1, SPAN):
        b, nxt, seen = min(hi, a + SPAN - 1), None, set()
        while True:
            d = rd.get(chain, "/events/range", **{"from": a, "to": b, "limit": 1000, "cursor": nxt})
            if not isinstance(d, dict): raise RuntimeError("the records route is not served on this host")
            evs += d.get("events") or []
            nxt = d.get("next_cursor")
            if not nxt: break
            if nxt in seen: raise RuntimeError(f"the records route repeated its next cursor {nxt}")
            seen.add(nxt)
    return evs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chain", help="a public node host that keeps the full record history (archive)")
    ap.add_argument("--minutes", type=float, default=10, help="window length, ending at the newest recorded height")
    ap.add_argument("--from-height", type=int); ap.add_argument("--to-height", type=int)
    ap.add_argument("--account"); ap.add_argument("--json"); ap.add_argument("--self-test")
    a = ap.parse_args()
    if a.self_test: return self_test(a.self_test)
    if not a.chain: ap.error("--chain is required")
    rd = Reader()
    try:
        cov = rd.get(a.chain, "/events/coverage") or {}
        rev = cov.get("records_schema_revision")
        if not isinstance(rev, int) or rev < 4:
            print(f"NOT RUN: this host's records are schema revision {rev!r}; balance records need 4 or later"); return 2
        if cov.get("archive") is not True: print("NOT RUN: this host is not an archive (it may have pruned records)"); return 2
        last = cov["last_height"]
        st = rd.get(a.chain, "/status") or {}
        rate = None
        hi = min(a.to_height, last) if a.to_height is not None else last
        if a.from_height is not None: lo = a.from_height
        else:
            h1, t1 = st.get("chain_head"), time.time(); time.sleep(5); h2 = (rd.get(a.chain, "/status") or {}).get("chain_head")
            rate = (h2 - h1) / (time.time() - t1) if isinstance(h1, int) and isinstance(h2, int) and h2 > h1 else None
            if not rate: print("NOT RUN: could not measure the chain's height rate"); return 2
            lo = max(1, int(hi - a.minutes * 60 * rate))
        start = cov.get("balance_chain_from")
        if start and lo < int(str(start).split(".")[0]):
            print(f"note: balance records start at {start}; the window starts there"); lo = int(str(start).split(".")[0])
        holes = [g for g in (cov.get("gaps") or []) + (cov.get("history_holes") or [])
                 if (g.get("after_height") or g.get("from") or 0) <= hi and (g.get("resumed_at") or g.get("to") or 0) >= lo]
        if holes: print(f"NOT RUN: the window {lo}-{hi} crosses a recorded gap {holes[0]}; pick a window outside it"); return 2
        evs = read_window(rd, a.chain, lo, hi)
        cache = {}
        def lookup(c):
            h = ckey(c)[0] if ckey(c) else None
            if h is None: return None
            if h not in cache:
                try: cache[h] = {e.get("cursor"): e for e in read_window(rd, a.chain, h, h)}
                except RuntimeError: cache[h] = {}
            return cache[h].get(c)
        money = {k.get("kind") for k in cov.get("money_record_kinds") or [] if isinstance(k, dict) and k.get("kind")} | MONEY
        problems, n, excl, kinds = replay(evs, lookup, _low(a.account), money)
    except (RuntimeError, OSError, KeyError, ValueError, TypeError, AttributeError) as x:
        print(f"NOT RUN: {x}"); return 2
    out = {"chain": a.chain, "from": lo, "to": hi, "rate_heights_per_s": rate, "records": len(evs), "reads": rd.count,
           "counts": dict(n), "excluded": dict(excl), "money_kinds_named": dict(kinds), "problems": problems,
           "result": "PROBLEM" if problems else ("PASS" if n["judged"] else "NOTHING JUDGED")}
    print(f"window {lo}-{hi} · {len(evs)} records · {n['changes']} balance changes · judged {n['judged']} · problems {len(problems)}")
    for k, v in sorted(excl.items()): print(f"  excluded {v:6d}  {k}")
    for k, v in sorted(kinds.items()): print(f"  named    {v:6d}  {k}")
    for p in problems[:50]: print("  PROBLEM  " + p)
    print("RESULT " + out["result"])
    if a.json:
        with open(a.json, "w") as f: json.dump(out, f, indent=1)
    return 1 if problems else (0 if n["judged"] else 3)


def self_test(path):
    """Each case: {name, events, outside (cursor -> record), expect: "pass" | "problem" | "excluded"}."""
    cases, bad = json.load(open(path)), 0
    for c in cases:
        outside = c.get("outside") or {}
        problems, n, excl, _ = replay(c["events"], lambda cur: outside.get(cur))
        got = "problem" if problems else ("pass" if n["judged"] else "excluded")
        ok = got == c["expect"]; bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {c['name']} (expect {c['expect']}, got {got}{': ' + problems[0] if problems and not ok else ''})")
    print(f"self-test: {'PASS' if not bad else 'FAIL'} ({len(cases)} cases)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
