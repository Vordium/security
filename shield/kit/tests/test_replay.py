#!/usr/bin/env python3
"""Tests for replay_balances.py: synthetic cases (each rule fires on its own planted fault; the clean case stays quiet), every
money record kind in the published fixtures parses into legs, and mutants of the checker are each caught by some case.
Usage: python3 tests/test_replay.py [fixtures-dir]"""
import copy, importlib.util, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)


def load(src=None):
    path = os.path.join(KIT, "replay_balances.py")
    spec = importlib.util.spec_from_loader("rb", loader=None); m = importlib.util.module_from_spec(spec)
    exec(compile(src if src is not None else open(path).read(), path, "exec"), m.__dict__)
    return m


A, B, T = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40


def side(usdc, res=0, pos=0, spot=0, col=None):
    return {"usdc_6dec": str(usdc), "reserved_orders_6dec": str(res), "in_positions_6dec": str(pos), "spot_reserved_6dec": str(spot),
            "collateral_6dec": str(usdc + res + pos + spot if col is None else col)}


def bc(cur, acct, before, after, recs, since=None, system=False, ux=None, rd=None, explained=None):
    d = int(after["collateral_6dec"]) - int(before["collateral_6dec"])
    rd = d if rd is None else rd; ux = d - rd if ux is None else ux
    return {"kind": "balance_change", "cursor": cur, "height": int(cur.split(".")[0]), "account": acct, "before": before, "after": after,
            "delta_6dec": str(d), "records_delta_6dec": str(rd), "unexplained_6dec": str(ux), "explained": (ux == 0) if explained is None else explained,
            "records": recs, "since_cursor": since, "system": system}


def fill(cur, t, td, m, md, tba=None, mba=None):
    return {"kind": "fill", "cursor": cur, "height": int(cur.split(".")[0]),
            "taker": {"account": t, "account_delta_6dec": str(td), **({"balance_after_6dec": str(tba)} if tba is not None else {})},
            "maker": {"account": m, "account_delta_6dec": str(md), **({"balance_after_6dec": str(mba)} if mba is not None else {})}}


def clean():
    return [fill("10.1.0", A, -50, B, 30, 950, 1030),
            bc("10.1.1", A, side(1000), side(950), ["10.1.0"], since="9.1.0"),
            bc("10.1.2", B, side(1000), side(1030), ["10.1.0"], since="9.1.1")]


OUT = {"9.1.0": bc("9.1.0", A, side(900), side(1000), [], since=None, rd=100), "9.1.1": bc("9.1.1", B, side(0), side(1000), [], rd=1000)}


def mut(fn):
    ev = clean(); fn(ev); return ev


CASES = [
    ("C1 clean: two legs of one fill, links read outside the window", clean(), OUT, "pass"),
    ("C2 a customer's unexplained change (chain's own figure)", mut(lambda e: e[1].update(records_delta_6dec="-40", unexplained_6dec="-10", explained=False)), OUT, "problem"),
    ("C3 explained flag contradicts the figure", mut(lambda e: e[1].update(explained=False)), OUT, "problem"),
    ("C4 before parts do not add up", mut(lambda e: e[1]["before"].update(usdc_6dec="999")), OUT, "problem"),
    ("C5 delta is not after - before", mut(lambda e: e[1].update(delta_6dec="-49", unexplained_6dec="1", explained=False)), OUT, "problem"),
    ("C5b delta alone is wrong (everything else consistent with it)",
     mut(lambda e: (e[1].update(delta_6dec="-49", records_delta_6dec="-49", unexplained_6dec="0"), e[0]["taker"].update(account_delta_6dec="-49"))), OUT, "problem"),
    ("C6 the named legs do not add to records_delta", mut(lambda e: e[0]["taker"].update(account_delta_6dec="-51")), OUT, "problem"),
    ("C7 the last leg's balance_after differs from after", mut(lambda e: e[0]["maker"].update(balance_after_6dec="1031")), OUT, "problem"),
    ("C8 link broken: before is not the previous after", clean(), {**OUT, "9.1.0": bc("9.1.0", A, side(900), side(999), [], rd=99)}, "problem"),
    ("C9 since_cursor names another account's change", clean(), {**OUT, "9.1.0": bc("9.1.0", B, side(900), side(1000), [], rd=100)}, "problem"),
    ("C10 a self-fill", [fill("10.1.0", A, -5, A, 3)], {}, "problem"),
    ("C11 system account unexplained: counted, not a customer problem",
     [bc("10.1.1", T, side(1000), side(1010), [], system=True, rd=0)], {}, "excluded"),
    ("C12 a leg the chain does not measure (notes_missing) is excluded, never 0",
     mut(lambda e: (e[0]["taker"].update(notes_missing=True), e.__delitem__(2))), OUT, "excluded"),
    ("C13 a named record that cannot be read is excluded", mut(lambda e: e.__delitem__(0)), OUT, "excluded"),
    ("C14 an unreadable record does not hide the chain's own unexplained figure",
     mut(lambda e: (e.__delitem__(0), e[0].update(records_delta_6dec="-40", unexplained_6dec="-10", explained=False))), OUT, "problem"),
    ("C15 gap record = new baseline; the next change links to it",
     [dict(bc("10.1.0", A, side(0), side(700), []), gap=True, gap_reason="dropped"),
      dict(fill("10.1.1", A, -20, B, 20)), bc("10.1.2", A, side(700), side(680), ["10.1.1"], since="10.1.0")], {}, "pass"),
    ("C16 a change after a gap that does not start at the gap's after",
     [dict(bc("10.1.0", A, side(0), side(700), []), gap=True, gap_reason="restore"),
      dict(fill("10.1.1", A, -20, B, 20)), bc("10.1.2", A, side(701), side(681), ["10.1.1"], since="10.1.0")], {}, "problem"),
    ("C17 legs[] wins over fill legs", [{"kind": "liquidation", "cursor": "10.1.0", "legs": [{"account": A, "account_delta_6dec": "-30"}, {"account": T, "account_delta_6dec": "30"}]},
                                        bc("10.1.1", A, side(100), side(70), ["10.1.0"])], {}, "pass"),
    ("C18 a record's own account_delta (funding)", [{"kind": "funding_payment", "cursor": "10.1.0", "account": A, "account_delta_6dec": "7"},
                                                    bc("10.1.1", A, side(100), side(107), ["10.1.0"])], {}, "pass"),
    ("C19 an empty window is never a pass", [], {}, "excluded"),
    ("C21 a change that skips the account's newest change",
     [{"kind": "funding_payment", "cursor": "10.1.0", "account": A, "account_delta_6dec": "5"}, bc("10.1.1", A, side(1000), side(1005), ["10.1.0"], since="9.1.0"),
      {"kind": "funding_payment", "cursor": "10.1.2", "account": A, "account_delta_6dec": "0"}, bc("10.1.3", A, side(1005), side(1005), ["10.1.2"], since="9.1.0")], OUT, "problem"),
    ("C22 a null since_cursor while the account's change comes before it (no reset)",
     [{"kind": "funding_payment", "cursor": "10.1.0", "account": A, "account_delta_6dec": "5"}, bc("10.1.1", A, side(1000), side(1005), ["10.1.0"], since="9.1.0"),
      {"kind": "funding_payment", "cursor": "10.1.2", "account": A, "account_delta_6dec": "1"}, bc("10.1.3", A, side(1005), side(1006), ["10.1.2"], since=None)], OUT, "problem"),
    ("C23 a money record naming no leg for the account is excluded, not read as 0",
     [{"kind": "deposit_credited", "cursor": "10.1.0", "account": B, "amount_6dec": "5"}, bc("10.1.1", A, side(1000), side(1000), ["10.1.0"], rd=0, since="9.1.0")], OUT, "excluded"),
    ("C24 an order record (no money) naming no leg adds 0 and is judged",
     [{"kind": "order_closed", "cursor": "10.1.0", "account": A}, bc("10.1.1", A, side(1000), side(1000), ["10.1.0"], rd=0, since="9.1.0")], OUT, "pass"),
    ("C20 a balance_reset starts the chain again (no link judged)",
     [{"kind": "deposit_credited", "cursor": "10.0.9", "account": A, "account_delta_6dec": "500"},
      bc("10.1.0", A, side(0), side(500), ["10.0.9"]), {"kind": "balance_reset", "cursor": "10.1.1", "accounts": []},
      {"kind": "funding_payment", "cursor": "10.1.2", "account": A, "account_delta_6dec": "5"}, bc("10.1.3", A, side(800), side(805), ["10.1.2"])], {}, "pass"),
]

# Not listed (equivalent: no verdict can change): dropping the stored gap baseline (the gap record is read in the window
# anyway) and ignoring a balance_reset (a change after a reset carries no since_cursor, so no link is judged).
MUTANTS = [
    ("unexplained never alarms", 'p.append(f"UNEXPLAINED {ux} micro-USDC', 'pass  # p.append(f"UNEXPLAINED {ux} micro-USDC'),
    ("legs total not compared", "if total != rd: p.append", "if False: p.append"),
    ("balance_after not compared", "if last_after is not None and last_after != ac:", "if False:"),
    ("link not compared (stored)", 'if bc != chains[acct][1]: p.append', 'if False: p.append'),
    ("link not compared (read)", "if bc != pa: p.append", "if False: p.append"),
    ("explained flag trusted", 'if e.get("explained") is not (ux == 0):', "if False:"),
    ("parts not checked", "if bs != bc: p.append", "if False: p.append"),
    ("delta not checked", "if d != ac - bc: p.append", "if False: p.append"),
    ("self-fill allowed", "if t and t == m:", "if False:"),
    ("notes_missing read as 0", 'if leg.get("notes_missing") is True or leg.get("account_delta_6dec") is None: measured = False; return',
     'if leg.get("account_delta_6dec") is None: return'),
    ("system account judged as a customer", 'elif measured or unrec: p.append(f"UNEXPLAINED', 'if measured or unrec: p.append(f"UNEXPLAINED'),
    ("wrong other-account link accepted", 'elif prev.get("kind") != "balance_change" or _low(prev.get("account")) != acct:', 'elif prev.get("kind") != "balance_change":'),
    ("unreadable record judged", "if missing: excl[", "if False: excl["),
    ("skipped newest change allowed", 'p.append(f"since_cursor {sc} skips', 'pass  # p.append(f"since_cursor {sc} skips'),
    ("null link after a change allowed", 'if acct in chains: p.append(f"since_cursor is null', 'if False: p.append(f"since_cursor is null'),
    ("money record without a leg read as 0", 'if not legs and r.get("kind") in money: unrec = True; continue', 'pass'),
    ("empty window passes", 'elif measured and not missing: n["judged"] += 1', 'else: n["judged"] += 1'),
]


def run(m, quiet):
    bad = 0
    for name, evs, outside, expect in CASES:
        problems, n, excl, _ = m.replay(copy.deepcopy(evs), lambda c, o=outside: copy.deepcopy(o.get(c)))
        got = "problem" if problems else ("pass" if n["judged"] else "excluded")
        if got != expect:
            bad += 1
            if not quiet: print(f"  FAIL  {name}: expect {expect}, got {got} {problems[:1]}")
        elif not quiet: print(f"  PASS  {name}")
    return bad


def main():
    m = load(); bad = run(m, False)
    fx = sys.argv[1] if len(sys.argv) > 1 else None
    if fx:
        kinds = 0
        for f in sorted(os.listdir(fx)):
            if not f.endswith(".json") or f in ("coverage.json",): continue
            d = json.load(open(os.path.join(fx, f))); recs = d if isinstance(d, list) else d.get("events") or d.get("records") or [d]
            for r in recs:
                if not isinstance(r, dict) or r.get("kind") in (None, "balance_change", "balance_reset"): continue
                accts = {(l or {}).get("account") for l in (r.get("legs") or [])} | {(r.get(s) or {}).get("account") for s in ("taker", "maker")} | {r.get("account")}
                try:
                    got = [m.legs_of(r, a.lower()) for a in accts if isinstance(a, str)]
                    kinds += 1
                except ValueError as x: bad += 1; print(f"  FAIL  fixture {f}: legs do not parse ({x})")
        print(f"  fixtures: {kinds} money records parsed into legs")
        bcs = []
        for f in ("balance_change.json", "balance_change_gap_dropped.json", "balance_change_gap_restore.json"):
            d = json.load(open(os.path.join(fx, f))); bcs += d if isinstance(d, list) else d.get("events") or [d]
        try:
            pr, n, ex, _ = m.replay([r for r in bcs if isinstance(r, dict)], lambda c: None)
            print(f"  fixtures: balance_change shapes read (changes {n['changes']}, problems {len(pr)}, excluded {dict(ex)})")
        except Exception as x: bad += 1; print(f"  FAIL  fixture balance_change shape: {x}")
    src = open(os.path.join(KIT, "replay_balances.py")).read(); killed = 0
    for name, a, b in MUTANTS:
        if src.count(a) != 1: print(f"  SITE NOT FOUND  {name}"); bad += 1; continue
        try: k = run(load(src.replace(a, b)), True) > 0
        except Exception: k = True
        print(f"  {'KILLED' if k else 'SURVIVED'}  {name}"); killed += k; bad += 0 if k else 1
    print(f"test_replay: {'PASS' if not bad else 'FAIL'} ({len(CASES)} cases, {killed}/{len(MUTANTS)} mutants killed)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
