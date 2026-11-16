#!/usr/bin/env python3
"""Vordium test network — public money replay.

Follows one or more accounts' collateral through their public chain records and checks, at every step, that the balance
the records predict equals the balance the chain reports. The same rule runs in the browser on the explorer's Replay page;
both are checked against the shared cases in cases.json (`money_replay.py --self-test cases.json`).

How a step is checked
  * A balance read is taken between two head reads (h1, h2). A balance only changes at the account's own records, so the
    read IS the balance at h1 when: the head did not go back (h2 >= h1), the records route has stored every height up to h2
    (coverage.last_height >= h2 and no listed gap in the window), and the account has no record inside [h1, h2].
  * Between two such reads (h0, h1), the change of  total + reserved_orders + in_positions  (free collateral + margin held
    by open orders + margin held by positions) must equal the sum over the account's records in (h0, h1] of:
        fill, this account's taker leg:  realized_pnl_6dec - fee_paid_6dec + rebate_6dec
        funding_payment:                 payment_6dec
        liquidation of kind "book":      - fee_6dec   (its realized PnL is already on the liquidation's own fill)
  * A taker fee above the listed rate (notional x taker_fee_cbps / 1e6, +1 for rounding) makes the step DIFFERENT.
  * NOT REPLAYABLE (never a match): a step with a MAKER leg (maker legs record no fee and no realized PnL yet), a
    liquidation of another kind (not confirmed against a real record yet), or any other record that names the account in
    any field (a deposit, a transfer's from/to, ...) and is not an order, stop or TWAP record.

Reads (public, no key): <chain>/status, <chain>/balance/<account>, <records>/events/account/<account>.
Usage:
  money_replay.py --minutes 30 [--step 15] [--chain URL] [--records URL] [--out trace.json] ACCOUNT [ACCOUNT ...]
  money_replay.py --self-test cases.json
Exit: 0 every replayable step matched (at least one) · 1 a step differs · 2 could not run · 3 nothing was checked.
"""
import argparse, json, sys, time, urllib.request


# ------------------------------------------------------------------ the rule (mirrors the explorer's lib/money-replay.ts)
def big(v):
    if v is None or v == "": return 0
    if isinstance(v, bool): raise ValueError(f"not a whole number: {v!r}")
    if isinstance(v, float): raise ValueError(f"not a whole number: {v!r}")
    s = str(v)
    if not s.lstrip("-").isdigit() or s.count("-") > (1 if s.startswith("-") else 0): raise ValueError(f"not a whole number: {s}")
    return int(s)


def low(v):
    return v.lower() if isinstance(v, str) else ""


def held(b):
    return big(b.get("total")) + big(b.get("reserved_orders")) + big(b.get("in_positions"))


def effect(e, acct):
    """(change, parts, unreplayable reason or None, taker fee above the list?)"""
    acct = acct.lower(); parts = []; why = None; above = False; k = e.get("kind")
    if k == "fill":
        if low((e.get("maker") or {}).get("account")) == acct: why = "maker leg: the record carries no fee and no realized PnL yet"
        bf = e.get("builder")
        if bf and ((low((e.get("taker") or {}).get("account")) == acct and big(bf.get("taker_fee_6dec")) != 0)
                   or (low((e.get("maker") or {}).get("account")) == acct and big(bf.get("maker_fee_6dec")) != 0)):
            why = why or "an app fee on this fill is not confirmed against a balance yet"
        if bf and ((low(bf.get("taker_builder")) == acct and big(bf.get("taker_fee_6dec")) != 0)
                   or (low(bf.get("maker_builder")) == acct and big(bf.get("maker_fee_6dec")) != 0)):
            why = why or "an app fee earned on this fill (it accrues to the builder's claimable balance) is not confirmed yet"
        L = e.get("taker") or {}
        if low(L.get("account")) == acct:
            parts += [("realized PnL", big(L.get("realized_pnl_6dec"))), ("fee", -big(L.get("fee_paid_6dec"))), ("rebate", big(L.get("rebate_6dec")))]
            cbps = (e.get("fee") or {}).get("taker_fee_cbps")
            if cbps is not None:
                listed = (big(e.get("size_18dec")) * big(e.get("price_8dec")) // 10 ** 20) * big(cbps) // 1_000_000
                if big(L.get("fee_paid_6dec")) > listed + 1: above = True
    elif k == "funding_payment" and low(e.get("account")) == acct:
        parts.append(("funding", big(e.get("payment_6dec"))))
    elif k == "liquidation" and low(e.get("account")) == acct:
        if e.get("liquidation") == "book": parts.append(("liquidation fee", -big(e.get("fee_6dec"))))
        else: why = f'a "{e.get("liquidation") or "unnamed"}" liquidation is not confirmed against a real record yet'
    elif not str(k or "").startswith(NO_MONEY) and names(e, acct):
        why = f'a "{k or "unnamed"}" record may move money and this replay does not read it yet'
    parts = [(n, x) for n, x in parts if x != 0]
    return sum(x for _, x in parts), parts, why, above


NO_MONEY = ("order_", "stop_", "twap_")     # record kinds that move no money; every other kind naming the account must be read


def names(e, acct):
    """the account appears anywhere in the record (any field, nested too: from, to, owner, ...)"""
    if isinstance(e, str): return low(e) == acct
    if isinstance(e, dict): return any(names(v, acct) for v in e.values())
    if isinstance(e, list): return any(names(v, acct) for v in e)
    return False


def _key(e):
    return tuple(int(x) for x in str(e.get("cursor", "")).split(".") if x.isdigit())


def unique_sorted(records):
    seen, out = set(), []
    for e in records:
        c = str(e.get("cursor") or "")
        if not c or c in seen: continue
        seen.add(c); out.append(e)
    return sorted(out, key=_key)


def covered(cov, lo, hi):
    if not isinstance(cov, dict) or cov.get("archive") is not True: return False
    last = cov.get("last_height")
    if not isinstance(last, int) or isinstance(last, bool) or last < hi: return False
    gaps = cov.get("gaps")
    if gaps is not None and not isinstance(gaps, list): return False
    for g in gaps or []:
        try:
            if not (int(g.get("resumed_at")) <= lo or int(g.get("after_height")) >= hi): return False
        except Exception: return False
    return True


def anchored(h1, h2, inside, cov):
    return isinstance(h1, int) and isinstance(h2, int) and h2 >= h1 and covered(cov, h1 - 1, h2) and len(inside) == 0


def step(acct, h0, b0, records, h1, b1):
    want = held(b0); why = None; above = False; rows = []
    for e in unique_sorted(records):
        h = e.get("height")
        if not isinstance(h, int) or isinstance(h, bool): raise ValueError("a record without a whole-number height")
        if not (h0 < h <= h1): continue
        d, parts, w, a = effect(e, acct)
        want += d; why = why or w; above = above or a
        if d or w: rows.append({"height": e["height"], "kind": e["kind"], "cursor": e.get("cursor"), "change": d,
                                "parts": [{"name": n, "amount": x} for n, x in parts], "note": w})
    got = held(b1)
    verdict = "not-replayable" if why else ("match" if got == want and not above else "different")
    return {"from": h0, "to": h1, "expected": want, "chain": got, "gap": got - want, "verdict": verdict, "rows": rows,
            "fee_above_list": above, "why": why}


def counts(s):
    return bool(s["rows"]) or s["chain"] != s["expected"]


# ------------------------------------------------------------------ reads
UA = {"user-agent": "vordium-money-replay/1"}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1: raise
            time.sleep(2 * (i + 1))


def main(a):
    accts = [x.lower() for x in a.accounts]
    def head():
        d = get(a.chain + "/status"); h = d.get("chain_head", d.get("height"))
        if not isinstance(h, int): raise RuntimeError("no chain head")
        return h
    def records(acct, lo, hi):
        """(records with lo < height <= hi, the route's coverage)"""
        out, cur, cov = [], None, None
        for _ in range(50):
            d = get(f"{a.records}/events/account/{acct}?limit=200&order=asc&from={lo + 1}&to={hi}" + (f"&cursor={cur}" if cur else ""))
            cov = d.get("coverage"); ev = d.get("events") or []
            out += ev; cur = d.get("next_cursor")
            if not cur or not ev: return out, cov
            time.sleep(0.25)
        raise RuntimeError("too many records in one step")
    trace = {"schema": "vordium.money-replay/2", "chain": a.chain, "records": a.records, "accounts": {}, "started": int(time.time())}
    anchor = {}
    end = time.time() + a.minutes * 60
    while time.time() < end:
        for acct in accts:
            h1 = head(); b = get(f"{a.chain}/balance/{acct}"); h2 = head()
            T = trace["accounts"].setdefault(acct, {"steps": [], "reads": 0, "unanchored_reads": 0})
            T["reads"] += 1
            inside, cov = records(acct, h1 - 1, h2)
            if not anchored(h1, h2, inside, cov): T["unanchored_reads"] += 1; continue
            if acct in anchor:
                h0, b0 = anchor[acct]
                ev, cov2 = records(acct, h0, h1)
                if not covered(cov2, h0, h1): T["unanchored_reads"] += 1; anchor.pop(acct, None); continue
                s = step(acct, h0, b0, ev, h1, b)
                if counts(s):
                    s["balance"] = b; T["steps"].append(s)
                    print(f"{acct[:10]}… {h0}→{h1}  expected {s['expected']}  chain {s['chain']}  {s['verdict']}", flush=True)
            anchor[acct] = (h1, b)
            time.sleep(0.5)
        time.sleep(a.step)
    trace["ended"] = int(time.time())
    s = [x for T in trace["accounts"].values() for x in T["steps"]]
    trace["summary"] = {"steps": len(s), "match": sum(x["verdict"] == "match" for x in s),
                        "not_replayable": sum(x["verdict"] == "not-replayable" for x in s),
                        "different": sum(x["verdict"] == "different" for x in s),
                        "reads": sum(T["reads"] for T in trace["accounts"].values()),
                        "unanchored_reads": sum(T["unanchored_reads"] for T in trace["accounts"].values())}
    json.dump(trace, open(a.out, "w"), indent=1)
    print("summary", json.dumps(trace["summary"]))
    if trace["summary"]["different"]: return 1
    return 0 if trace["summary"]["match"] else 3


def self_test(path):
    """the shared cases: each names its inputs and the verdict both implementations must give"""
    cases = json.load(open(path)); bad = 0
    for c in cases["steps"]:
        try: v = step(c["account"], c["h0"], c["b0"], c["records"], c["h1"], c["b1"])["verdict"]
        except Exception as x: v = f"error {type(x).__name__}"
        ok = v == c["verdict"] or (c["verdict"] == "error" and v.startswith("error"))
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {c['name']}  ({v})")
    for c in cases.get("anchors", []):
        v = anchored(c["h1"], c["h2"], c["inside"], c["coverage"]); ok = v == c["anchored"]; bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {c['name']}  ({v})")
    print(f"self-test: {'PASS' if not bad else f'FAIL ({bad})'}")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test": sys.exit(self_test(sys.argv[2]))
    ap = argparse.ArgumentParser(description="public money replay (test network)")
    ap.add_argument("accounts", nargs="+")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--step", type=float, default=15, help="seconds between balance reads of one account")
    ap.add_argument("--chain", default="https://testnet.vordex.xyz/chain")
    ap.add_argument("--records", default="https://testnet.vordex.xyz/chain-archive")
    ap.add_argument("--out", default="money-replay-trace.json")
    args = ap.parse_args()
    try: sys.exit(main(args))
    except Exception as x:
        print(f"could not run: {type(x).__name__}: {x}"); sys.exit(2)
