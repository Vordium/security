"""C-18..C-21 (Python SDK): signing against the published test vectors and the chain's own type strings.

C-18 the official agent-op vectors (github.com/Vordium/node, vectors/agent-ops-vectors-2c1c0679.json): the SDK's domain
     and its type definitions rebuild every digest, and its signatures with the public test keys equal the vectors'.
C-19 every type string the network spec publishes equals the Python SDK's.
C-20 the test-network vectors (../vectors/testnet-signing-vectors.json, made by the JS SDK): the Python SDK's OWN code
     paths (struct hashes of orders, cancels, stop-all, TWAP, sessions, builder fees, agents) give the same type string
     and digest for every operation, and each stored signature recovers to the public test key: two independent
     implementations agree.
C-21 withdrawals (WithdrawIntentV4, Python only): the SDK's signable message equals an independent encoding.

Run:  python3 this file   (pip install vordium; reads two public URLs; --vectors FILE for a local copy)
Exit: 0 all equal, 1 a mismatch, 3 cannot run.
"""
import json
import os
import re
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kit import TESTNET_GENESIS, Results, get_json  # noqa: E402

warnings.simplefilter("ignore")
try:
    import vordium
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from eth_utils import keccak
    from vordium import account_ops as ao, builder, caps, domains, eip712, mm, bridge_v4
except Exception as e:  # pragma: no cover
    print(f"cannot import vordium: {e}")
    sys.exit(3)

from vordium.pins import PINS as _P  # noqa: E402
PINS_MAIN = _P["mainnet"].genesis_sha256
R = Results(f"C-18..C-21 signing vectors, Python SDK vordium {vordium.__version__}")
HERE = os.path.dirname(os.path.abspath(__file__))
OFFICIAL = "https://raw.githubusercontent.com/Vordium/node/main/vectors/agent-ops-vectors-2c1c0679.json"
SPECS = {"testnet": "https://testnet.vordex.xyz/network-spec.json", "mainnet": "https://rpc.vordium.com/network-spec.json"}


def ts_from_fields(name, fields):
    return f"{name}(" + ",".join(f"{t} {n}" for n, t in fields) + ")"


def parse_ts(s):
    """'A(t n,..)B(..)' -> {A: [{name,type}], B: [...]}"""
    out = {}
    for m in re.finditer(r"([A-Za-z0-9]+)\(([^()]*)\)", s):
        out[m.group(1)] = [{"name": f.split(" ")[1], "type": f.split(" ")[0]} for f in m.group(2).split(",") if f]
    return out


# The Python SDK's own type strings, gathered from its modules
PY_TS = {}
for op, fields in eip712.TYPES.items():
    PY_TS[op] = ts_from_fields(op, [(f["name"], f["type"]) for f in fields])
for op, fields in (("SessionCreate", ao.SESSION_CREATE), ("SessionRevoke", ao.SESSION_REVOKE), ("PlaceTwap", ao.PLACE_TWAP),
                   ("CancelTwap", ao.CANCEL_TWAP), ("SetMarginMode", ao.SET_MARGIN_MODE)):
    PY_TS[op] = ts_from_fields(op, fields)
PY_TS.update(builder.TYPES)
PY_TS["BatchOrders"] = mm._BATCH_TYPE
PY_TS["CancelAllOrders"] = mm._CANCEL_ALL_TYPE
PY_TS["ModifyOrderV2"] = mm._MODIFY_V2_TYPE
PY_TS["SetMmp"] = mm._SET_MMP_TYPE
PY_TS["ScheduleCancel"] = "ScheduleCancel(address owner,uint64 cancelAtMs,uint64 nonce)"
PY_TS["WithdrawIntentV4"] = bridge_v4.WITHDRAW_INTENT_TYPE
# the hard-coded type hashes inside the SDK must hash these strings
R.check("C-19x ScheduleCancel type hash inside the SDK", caps._SCHEDULE_CANCEL_TYPEHASH == keccak(PY_TS["ScheduleCancel"].encode()))
R.check("C-19x builder type hashes inside the SDK", all(builder.TYPEHASHES[k] == "0x" + keccak(v.encode()).hex()
                                                         for k, v in builder.TYPES.items()))
R.check("C-19x SetMarginMode type hash inside the SDK", ao.SET_MARGIN_MODE_TYPEHASH == "0x" + keccak(PY_TS["SetMarginMode"].encode()).hex())


def typed_digest(dom, primary, tstring, message):
    types = parse_ts(tstring)
    m = encode_typed_data(domain_data=dom, message_types=types, message_data=message)
    return "0x" + keccak(b"\x19\x01" + m.header + m.body).hex(), m


def offline_network(name):
    """A resolved network for the SDK's own signers, offline: the named network's pin, nothing read."""
    from vordium import network as N
    from vordium.pins import PINS
    p = PINS[name]
    return N.Network(chain_id=p.chain_id, genesis_sha256=p.genesis_sha256, chain_id_hex=hex(p.chain_id), chain_name=name,
                     rpc_url="http://x.invalid", ws_url=None, explorer_url=None, bridge_address=None, bridge_chain=None,
                     bridge_chain_id=None, native_symbol="VORD", native_decimals=18,
                     verifying_contract=domains.VERIFYING_CONTRACT, source="kit", chain_id_sources={}, name=name)


def ints(v):
    """JSON vector values: numbers are decimal strings."""
    if isinstance(v, dict):
        return {k: ints(x) for k, x in v.items()}
    if isinstance(v, list):
        return [ints(x) for x in v]
    if isinstance(v, str) and re.fullmatch(r"\d+", v):
        return int(v)
    return v


# ── C-18 official vectors ──────────────────────────────────────────────────────────────────────────────────────────
off = None
try:
    if "--vectors" in sys.argv:
        off = json.load(open(sys.argv[sys.argv.index("--vectors") + 1]))
    else:
        off = get_json(OFFICIAL)
except Exception as e:
    R.skip("C-18 official vectors", f"cannot read them: {e}")
if off:
    g, cid = off["network"]["genesis_sha256"], off["domain"]["chainId"]
    dom = domains.domain("VordCore", cid, g)
    R.check("C-18a domain separator", "0x" + domains.separator("VordCore", cid, g).hex() == off["domain"]["domainSeparator"])
    for part in ("canonical_vectors", "signed_vectors"):
        for v in off[part]["vectors"]:
            d, m = typed_digest(dom, v["op"], PY_TS[v["op"]], ints(v["message"]))
            R.check(f"C-18b {part.split('_')[0]} {v['op']} digest", d == v["digest"], v["digest"])
            if part == "signed_vectors" and cid == 101101 and g == PINS_MAIN:
                from vordium import network as N
                N.set_network(offline_network("mainnet"))
                try:
                    d_sdk = eip712.digest(v["op"], ints(v["message"]))
                    R.check(f"C-18b' {v['op']} digest through the SDK signer path", d_sdk == v["digest"])
                    for c in v["cases"]:
                        if c["expected"].startswith("ACCEPTED") and "owner" in c["signedBy"]:
                            s = eip712.sign_agent_op(off["test_keys"]["owner"]["private_key"], v["op"], ints(v["message"]))
                            R.check(f"C-18c {v['op']} signature made by the SDK (sign_agent_op) with the public owner test key",
                                    s.lower() == c["signature"].lower())
                finally:
                    N.reset_network()

# ── C-19 published type strings ────────────────────────────────────────────────────────────────────────────────────
n_compared = 0
for net, url in SPECS.items():
    try:
        spec = get_json(url)
    except Exception as e:
        R.skip(f"C-19 {net} spec", str(e))
        continue
    found = []

    def walk(x, p):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, p + "/" + k)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{p}/{i}")
        elif isinstance(x, str) and re.match(r"^[A-Z][A-Za-z0-9]*\((?:[a-z0-9\[\]]+ [A-Za-z0-9]+,?)*\)", x) and \
                re.search(r"\b(uint|address|bytes32|bool)", x):
            found.append((p, x))
    walk(spec, "")
    if not found:
        print(f"[note] the {net} spec publishes no type strings: nothing to compare there")
    for p, ts in found:
        name = ts[:ts.index("(")]
        if name not in PY_TS:
            print(f"[note] {net}{p}: {name} is published but the Python SDK does not sign it")
            continue
        n_compared += 1
        R.check(f"C-19 {net} spec {name} type string equals the SDK's", ts == PY_TS[name], p)

R.check("C-19 the network specs published at least one type string to compare", n_compared > 0, f"{n_compared} compared")

# no two operations share a field list (one signature can never verify as two ops in one domain)
seen = {}
for op, ts in PY_TS.items():
    body = ts[ts.index("("):ts.index(")") + 1]
    seen.setdefault(body, []).append(op)
dups = {k: v for k, v in seen.items() if len(v) > 1}
R.check(f"C-35 no two of the SDK's {len(PY_TS)} operations share a field list", not dups, str(dups)[:200])

# ── C-20 test-network vectors made by the JS SDK ──────────────────────────────────────────────────────────────────
path = os.path.join(HERE, "testnet-signing-vectors.json")
try:
    tv = json.load(open(path))
except Exception as e:
    tv = None
    R.skip("C-20 test-network vectors", f"{path}: {e}")
if tv:
    seps = {c: domains.separator(c, 101102, TESTNET_GENESIS) for c in ("VordCore", "VordexSession")}
    R.check("C-20a domain separators", all("0x" + seps[c].hex() == tv["domains"][c]["separator"] for c in seps))
    addr = tv["testKey"]["address"]

    def dg(cls, sh):
        return "0x" + keccak(b"\x19\x01" + seps[cls] + sh).hex()

    def sdk_digest(op, m):
        """The digest through the SDK's own code path for this op (None when it has only a generic one)."""
        if op == "PlaceOrder":
            return dg("VordCore", caps.place_order_struct_hash(m["owner"], m["pairId"], m["side"], m["size"], m["price"],
                                                               m["leverageBps"], m["orderType"], m["reduceOnly"],
                                                               m["clientNonce"], m["postOnly"], m["triggerPrice8dec"],
                                                               m["triggerDir"]))
        if op == "CancelOrder":
            return dg("VordCore", caps.cancel_order_struct_hash(m["owner"], m["orderId"]))
        if op == "SetTpSl":
            return dg("VordCore", caps.set_tpsl_struct_hash(m["owner"], m["pairId"], m["positionId"], m["takeProfit8dec"],
                                                            m["stopLoss8dec"]))
        if op == "ScheduleCancel":
            return dg("VordCore", caps.schedule_cancel_struct_hash(m["owner"], m["cancelAtMs"], m["nonce"]))
        if op == "CancelAllOrders":
            return dg("VordCore", mm.cancel_all_struct_hash(m["owner"], m["pairId"], m["nonce"]))
        if op == "ModifyOrderV2":
            return dg("VordCore", mm.modify_v2_struct_hash(m["owner"], m["orderId"], m["newPrice"], m["newSize"],
                                                           m["clientNonce"]))
        if op in builder.TYPES:
            return dg("VordCore", builder.struct_hash(op, m))
        lists = {"SessionCreate": ("VordexSession", ao.SESSION_CREATE), "SessionRevoke": ("VordexSession", ao.SESSION_REVOKE),
                 "PlaceTwap": ("VordCore", ao.PLACE_TWAP), "CancelTwap": ("VordCore", ao.CANCEL_TWAP),
                 "SetMarginMode": ("VordCore", ao.SET_MARGIN_MODE)}
        if op in lists:
            cls, fields = lists[op]
            return "0x" + ao.digest(seps[cls], op, fields, m).hex()
        if op in eip712.TYPES:
            from vordium import network as N
            N.set_network(offline_network("testnet"))
            try:
                return eip712.digest(op, m)
            finally:
                N.reset_network()
        return None
    for v in tv["vectors"]:
        op, m = v["op"], ints(v["message"])
        R.check(f"C-20 {op}: Python type string equals the vector's", PY_TS.get(op) == v["typeString"],
                "missing in the Python SDK" if op not in PY_TS else "")
        d = sdk_digest(op, m)
        how = "SDK code path"
        if d is None and op in PY_TS:
            d, _ = typed_digest(domains.domain(v["domainClass"], 101102, TESTNET_GENESIS), op, PY_TS[op], m)
            how = "generic encoder on the SDK's type string"
        R.check(f"C-20 {op}: Python digest equals the JS vector ({how})", d == v["digest"], v["digest"])
        rec = Account._recover_hash(bytes.fromhex(v["digest"][2:]), signature=bytes.fromhex(v["signature"][2:]))
        R.check(f"C-20 {op}: stored signature recovers to the public test key", rec == addr)

# ── C-21 withdrawal intent ─────────────────────────────────────────────────────────────────────────────────────────
try:
    from vordium.bridge_v4 import WithdrawIntent
    import inspect
    params = list(inspect.signature(WithdrawIntent).parameters)
    i = WithdrawIntent(**{p: v for p, v in dict(account="0x" + "11" * 20, vault_id=1, recipient="0x" + "00" * 12 + "22" * 20,
                                                 amount=25_000_000, nonce=3, route_kind=0, destination_domain=3,
                                                 max_fee=0, deadline=1_900_000_000).items() if p in params})
    msg = bridge_v4.withdraw_intent_message(i)
    msg["recipient"] = bytes.fromhex(i.recipient[2:])
    d_ind, _ = typed_digest(domains.domain("VordCore", 101102, TESTNET_GENESIS), "WithdrawIntentV4", PY_TS["WithdrawIntentV4"], msg)
    from vordium import network as N
    N.set_network(N.Network(chain_id=101102, genesis_sha256=TESTNET_GENESIS, chain_id_hex="0x18aee", chain_name="t",
                            rpc_url="http://x.invalid", ws_url=None, explorer_url=None, bridge_address=None, bridge_chain=None,
                            bridge_chain_id=None, native_symbol="VORD", native_decimals=18,
                            verifying_contract=domains.VERIFYING_CONTRACT, source="kit", chain_id_sources={}, name="testnet"))
    try:
        orig = bridge_v4._require_open
        bridge_v4._require_open = lambda: None       # the signer itself, not the route's open/closed state
        m = bridge_v4.withdraw_intent_signable(i)
        d_sdk = "0x" + keccak(b"\x19\x01" + m.header + m.body).hex()
    finally:
        bridge_v4._require_open = orig
        N.reset_network()
    R.check("C-21 WithdrawIntentV4: SDK signable equals an independent encoding (test-network domain)", d_sdk == d_ind, d_sdk)
except Exception as e:
    R.check("C-21 WithdrawIntentV4 encoding", False, f"{type(e).__name__}: {e}")
R.finish()
