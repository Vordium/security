#!/usr/bin/env python3
"""Public money replay, version 2: each account's collateral follows the network's public money records, step by step.

The network writes one `balance_change` record per account per change: the collateral before and after (usdc,
reserved_orders, in_positions, spot_reserved) and the cursors of the money records that made the change (`records`).
Every money record says what it moved each account by (its legs: `account_delta_6dec`). For each step this script checks

    collateral before + the sum of this account's legs in the records it names = collateral after

and, where the account's previous step was read, that this step starts where that one ended (before = previous after).
The money record kinds are read from <records>/events/coverage (money_record_kinds), never from a list in this script.
A step is:
  match          it adds up, it starts where the previous step ended, and the record's own totals agree
  different      it does not add up, the record's own totals disagree, a part is not a number, or the chain is broken
  unexplained    the network itself marks the step unexplained (explained false or unexplained_6dec not 0); never a match
  not checked    a gap record (dropped / restore), a reset, a leg that could not be measured (notes_missing) or a record
                 it names that was not read; shown with why, never a match
Reads (public, no key): <records>/events/coverage, <records>/events/account/<account>.
Exit: 0 every checked step matched (at least one) and no account outside the protocol's own has an unexplained step
      1 a step differs, or a non-protocol account has an unexplained step · 2 could not run · 3 nothing was checked
Self-test: python3 balance_replay.py --self-test CASES.json  (0 every case gives its listed verdicts · 1 a case does not)
"""
import argparse, json, sys, urllib.request

VERSION = "2.1"
NEEDS_REVISION = 4
PARTS = ("usdc_6dec", "reserved_orders_6dec", "in_positions_6dec", "spot_reserved_6dec")
UA = {"User-Agent": "vordium-balance-replay/2.1"}
ZERO_KINDS = ("order_closed", "order_updated")   # named order records: they move margin inside collateral only


def has_6dec(v):
    """True when any key at any depth names an amount in micro-USDC."""
    if isinstance(v, dict):
        return any("6dec" in str(k) or has_6dec(x) for k, x in v.items())
    if isinstance(v, list):
        return any(has_6dec(x) for x in v)
    return False


def big(v):
    """An amount: a decimal string or an integer, never a float or a bool. None when it is not one."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


def low(v):
    return v.lower() if isinstance(v, str) else v


def key(e):
    return tuple(int(x) for x in str(e.get("cursor", "")).split(".") if x.isdigit())


def collateral(side):
    """(sum of the four parts, the side's own collateral_6dec) in micro-USDC; (None, _) when a part is not a number."""
    if not isinstance(side, dict):
        return None, None
    vals = [big(side.get(p)) for p in PARTS]
    return (None if any(v is None for v in vals) else sum(vals)), big(side.get("collateral_6dec"))


def legs(rec):
    """The legs of one money record: its `legs` list, else its taker / maker blocks, else the record itself."""
    if isinstance(rec.get("legs"), list):
        return [x for x in rec["legs"] if isinstance(x, dict)]
    sides = [rec[s] for s in ("taker", "maker") if isinstance(rec.get(s), dict)
             and (rec[s].get("account") or "account_delta_6dec" in rec[s] or rec[s].get("notes_missing") is True)]
    if sides:
        return sides
    return [rec] if "account_delta_6dec" in rec else []


def account_legs(rec, acct):
    """This account's change in one record: (sum, a leg was not measured, a leg is not a number)."""
    s, missing, bad = 0, rec.get("notes_missing") is True, False
    for leg in legs(rec):
        if low(leg.get("account")) != acct:
            continue
        if leg.get("notes_missing") is True:
            missing = True
            continue
        d = big(leg.get("account_delta_6dec"))
        if d is None:
            bad = True   # a leg of this account with no amount is never read as zero
        else:
            s += d
    return s, missing, bad


def replay(acct, records, money_kinds):
    """Every balance_change of one account, judged. Pure: the records in, one row per step out."""
    acct = low(acct)
    uniq = {json.dumps(e, sort_keys=True): e for e in records if isinstance(e, dict) and e.get("cursor") is not None}
    recs = sorted(uniq.values(), key=key)   # identical copies collapse; two different records on one cursor both stay
    by_cursor = {}
    for e in recs:
        by_cursor.setdefault(str(e.get("cursor")), []).append(e)
    seen_bc = {}
    for e in recs:
        if e.get("kind") == "balance_change" and low(e.get("account")) == acct:
            seen_bc[str(e.get("cursor"))] = seen_bc.get(str(e.get("cursor")), 0) + 1
    rows, prev = [], None
    for e in recs:
        kind = e.get("kind")
        if kind == "balance_reset":
            prev = None   # steps before a reset are not chained to steps after it
            continue
        if kind != "balance_change" or low(e.get("account")) != acct:
            continue
        row = {"cursor": e.get("cursor"), "height": e.get("height"), "system": e.get("system") is True}
        if e.get("gap"):
            row.update(verdict="not checked", why=f"gap record ({e.get('gap_reason') or 'gap'}): never checked across")
            rows.append(row); prev = None; continue
        (before, b_own), (after, a_own) = collateral(e.get("before")), collateral(e.get("after"))
        named = e.get("records") if isinstance(e.get("records"), list) else None
        s, missing, bad, unread, n, shared, nonmoney = 0, False, False, [], 0, [], []
        twice = named is not None and len({str(c) for c in named}) != len(named)
        for c in dict.fromkeys(str(c) for c in named or []):
            hits = [r for r in by_cursor.get(c, []) if r.get("kind") in money_kinds]
            if not hits:
                other = by_cursor.get(c, [])
                # a named record of a kind that moves no collateral (ZERO_KINDS: an order closing or changing size moves
                # margin between reserved_orders and usdc) counts as zero legs. Only when exactly one record sits on that cursor,
                # it names this account, it has no leg of any shape and no micro-USDC amount at any depth; anything
                # else stays "not checked".
                if (len(other) == 1 and other[0].get("kind") in ZERO_KINDS
                        and acct in [low(x) for x in (other[0].get("accounts") or [])]
                        and not any(k in other[0] for k in ("legs", "taker", "maker", "notes_missing"))
                        and not legs(other[0]) and not has_6dec(other[0])):
                    nonmoney.append(c); continue
                unread.append(c); continue
            if len(hits) > 1:
                shared.append(c); continue
            for r in hits:
                d, m, b = account_legs(r, acct)
                s += d; missing |= m; bad |= b; n += 1
        row.update(records=n, legs_6dec=str(s), named_without_money=len(nonmoney))
        prev_after = collateral(prev.get("after"))[0] if prev is not None else None
        since = e.get("since_cursor")
        linked = prev is not None and since is not None and str(since) == str(prev.get("cursor"))
        unexpl = e.get("unexplained_6dec")
        if named is None:
            row.update(verdict="different", why="the record does not name its money records")
        elif seen_bc.get(str(e.get("cursor")), 0) > 1:
            row.update(verdict="different", why="two different balance records for this account on one cursor")
        elif before is None or after is None or bad:
            row.update(verdict="different", why="a balance part or a leg amount is not a number")
        elif (b_own is not None and b_own != before) or (a_own is not None and a_own != after):
            row.update(verdict="different", why="collateral_6dec is not the sum of its four parts")
        elif unexpl is not None and big(unexpl) is None:
            row.update(verdict="different", why="unexplained_6dec is not a number")
        elif e.get("explained") is False or (big(unexpl) or 0) != 0:
            row.update(verdict="unexplained", why=f"the network marks {unexpl} micro-USDC unexplained")
        elif missing:
            row.update(verdict="not checked", why="a leg it names could not be measured (notes_missing)")
        elif twice or shared:
            row.update(verdict="not checked", why="it names a record twice, or two different records share a cursor it names")
        elif unread:
            row.update(verdict="not checked", why=f"a record it names was not read: {', '.join(unread[:3])}")
        # the step's own sum and totals are judged before the chain: a step that does not add up is always "different"
        elif before + s != after:
            row.update(verdict="different", why=f"before {before} + legs {s} = {before + s}, but after is {after}")
        elif big(e.get("delta_6dec")) not in (None, after - before) or big(e.get("records_delta_6dec")) not in (None, s):
            row.update(verdict="different", why="the record's own delta_6dec or records_delta_6dec disagrees with the replay")
        elif prev is not None and since is not None and not linked:
            row.update(verdict="different", why=f"chain broken: since_cursor {since} is not the account's previous step {prev.get('cursor')}")
        elif linked and prev_after != before:
            row.update(verdict="different", why=f"chain broken: before {before} is not the previous step's after {prev_after}")
        elif prev is not None and since is None:
            row.update(verdict="not checked", why="the step adds up, but it starts a new chain (no since_cursor): the move from the previous step is not checked")
        else:
            row.update(verdict="match", chained=linked)
        row.update(before_6dec=str(before), after_6dec=str(after))
        rows.append(row)
        prev = e
    return rows


def counts(rows):
    c = {"match": 0, "different": 0, "unexplained": 0, "not checked": 0, "unexplained_outside_system": 0}
    for r in rows:
        c[r["verdict"]] += 1
        if r["verdict"] == "unexplained" and not r.get("system"):
            c["unexplained_outside_system"] += 1
    return c


def exit_code(c):
    if c["different"] or c["unexplained_outside_system"]:
        return 1
    return 0 if c["match"] else 3


def kinds_of(cov):
    """The money record kinds as the records list them (objects with a `kind`, or plain names)."""
    out = set()
    for k in cov.get("money_record_kinds") or []:
        name = k.get("kind") if isinstance(k, dict) else k
        if isinstance(name, str):
            out.add(name)
    return out


def get(url, tries=3):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except Exception as ex:   # noqa: BLE001 — a public read: report it and stop, never guess
            last = ex
    raise RuntimeError(f"{url}: {last}")


def main(a):
    try:
        cov = get(f"{a.records}/events/coverage")
    except RuntimeError as ex:
        print(f"could not run: {ex}"); return 2
    if cov.get("records_schema_revision") != NEEDS_REVISION:
        print(f"could not run: the records are revision {cov.get('records_schema_revision')!r}; this version reads revision {NEEDS_REVISION}")
        return 2
    kinds = kinds_of(cov)
    if not kinds:
        print("could not run: the records do not list their money record kinds"); return 2
    hi = a.to_height if a.to_height is not None else cov.get("last_height")
    if not isinstance(hi, int):
        print("could not run: no last height in the records"); return 2
    lo = a.from_height if a.from_height is not None else max(0, hi - a.blocks)
    out, total = {"version": VERSION, "records": a.records, "from_height": lo, "to_height": hi, "accounts": {}}, None
    for acct in a.accounts:
        recs, cur, seen = [], None, set()
        while True:
            try:
                d = get(f"{a.records}/events/account/{acct}?limit=200&order=asc&from={lo}&to={hi}" + (f"&cursor={cur}" if cur else ""))
            except RuntimeError as ex:
                print(f"could not run: {ex}"); return 2
            recs += d.get("events") or []
            cur = d.get("next_cursor")
            if not cur:
                break
            if cur in seen or len(seen) >= 10000:
                print(f"could not run: the records for {acct} do not finish paging"); return 2
            seen.add(cur)
        rows = replay(acct, recs, kinds)
        c = counts(rows)
        out["accounts"][acct] = {"counts": c, "steps": rows}
        total = c if total is None else {k: total[k] + c[k] for k in c}
        print(f"{acct}: {c['match']} match · {c['different']} different · {c['unexplained']} unexplained · {c['not checked']} not checked")
    out["summary"] = total
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
    print(f"heights {lo:,}–{hi:,}: " + " · ".join(f"{v} {k}" for k, v in total.items()) + f" — trace {a.out}")
    return exit_code(total)


def self_test(path):
    with open(path) as f:
        cases = json.load(f)
    kinds = kinds_of(cases["coverage"])
    bad = 0
    for c in cases["cases"]:
        got = [r["verdict"] for r in replay(c["account"], c["records"], kinds)]
        ok = got == c["expect"]
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {c['name']}" + ("" if ok else f"  (got {got}, want {c['expect']})"))
    print("self-test: " + ("PASS" if not bad else f"FAIL ({bad})"))
    return 0 if not bad else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="public money replay, version 2 (balance records, revision 4)")
    ap.add_argument("accounts", nargs="*")
    ap.add_argument("--blocks", type=int, default=20000, help="how many recent heights to check (default 20000)")
    ap.add_argument("--from-height", type=int)
    ap.add_argument("--to-height", type=int)
    ap.add_argument("--records", default="https://testnet.vordex.xyz/chain-archive")
    ap.add_argument("--out", default="balance-replay-trace.json")
    ap.add_argument("--self-test", metavar="CASES")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test(a.self_test))
    if not a.accounts:
        ap.error("name at least one account")
    sys.exit(main(a))
