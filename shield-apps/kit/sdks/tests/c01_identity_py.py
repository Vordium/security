"""C-01..C-07 (Python SDK): chain id and genesis pinning against a hostile node.

A local node on 127.0.0.1 claims one identity after another. For each, the SDK is asked to sign an order (the full
`Vordex.place_order` path) and to build its signing domain. The defence holds when every hostile identity is refused
before anything is signed or sent, and the real test-network identity (the positive control) is signed for.

Run:  python3 this file        (needs: pip install vordium; no network access)
Exit: 0 = defended, 1 = an identity was signed for, 3 = cannot run.
"""
import os
import secrets
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kit import MAINNET_GENESIS, TESTNET_GENESIS, Results, Stub, clean_env  # noqa: E402

warnings.simplefilter("ignore")
clean_env()
try:
    import vordium
    from eth_account import Account
    from vordium import network as N, eip712, units
    from vordium.dex import Vordex, BUY, LIMIT
except Exception as e:  # pragma: no cover
    print(f"cannot import vordium: {e}")
    sys.exit(3)

R = Results(f"C-01..C-07 chain id + genesis pinning, Python SDK vordium {vordium.__version__}")
OWNER = Account.create()
SESSION = Account.create()


def signs_order(stub: Stub, network) -> tuple:
    """(signed_or_sent, why): place one order through a client pointed at the stub."""
    stub.routes[("POST", "/order/place")] = (200, {"status": "submitted"})
    before = sum(1 for r in stub.log if r["path"] == "/order/place")
    try:
        vx = Vordex(rpc_url=stub.base, network=network, specs=units.NO_RULES, chain_clock=None, timeout=3)
        vx.place_order(session_key=SESSION.key.hex(), owner=OWNER.address, pair_id=1, side=BUY, size="0.01",
                       price="1000", order_type=LIMIT, retries=1)
    except Exception as e:
        sent = sum(1 for r in stub.log if r["path"] == "/order/place") - before
        return sent > 0, f"{type(e).__name__}: {str(e)[:110]}"
    sent = sum(1 for r in stub.log if r["path"] == "/order/place") - before
    return True, f"order sent ({sent} copy)"


def domain_built(net) -> tuple:
    try:
        N.set_network(net)
        d = eip712.domain()
        return True, f"domain chainId {d['chainId']}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:110]}"
    finally:
        N.reset_network()


def case(name, chain_id, genesis, network="testnet", rpc_chain_id=None, expect_sign=False, rest_only_ok=False):
    with Stub() as s:
        s.identity(chain_id, genesis, rpc_chain_id=rpc_chain_id)
        net = None
        try:
            net = N.resolve_network(rpc_url=s.base, network=network, timeout=3)
        except Exception as e:
            resolved = f"resolve refused: {type(e).__name__}"
        else:
            resolved = "resolved"
        dom_ok, dom_why = domain_built(net) if net is not None else (False, resolved)
        sent, why = signs_order(s, network)
        if expect_sign:
            R.check(f"{name}: control is signed for", dom_ok and sent, f"{dom_why}; {why}")
        elif rest_only_ok:
            # the order path talks REST only: it reads /status (which here equals the pin) and signs under the PIN, so
            # what it signs is valid on the pinned network alone; the JSON-RPC path must still refuse
            R.check(f"{name}: JSON-RPC path refuses; order path signs only under the pin", not dom_ok,
                    f"{resolved}; {dom_why}; order path: {why}")
        else:
            R.check(f"{name}: nothing signed or sent", not dom_ok and not sent, f"{resolved}; {dom_why}; {why}")


# positive control: the real test-network identity
case("C-00 control (testnet identity, network='testnet')", 101102, TESTNET_GENESIS, expect_sign=True)
# C-01 another chain id
case("C-01 node answers mainnet chain id 101101 for 'testnet'", 101101, TESTNET_GENESIS)
case("C-01b eth_chainId disagrees with /status", 101102, TESTNET_GENESIS, rpc_chain_id=101101, rest_only_ok=True)
# C-02 another genesis, same chain id
case("C-02 node answers a foreign genesis for 'testnet'", 101102, secrets.token_hex(32))
case("C-02b node answers the mainnet genesis with testnet chain id", 101102, MAINNET_GENESIS)
case("C-02c node answers a foreign genesis with the main chain id for 'mainnet'", 101101, secrets.token_hex(32), network="mainnet")
case("C-02d node answers the test genesis with the main chain id for 'mainnet'", 101101, TESTNET_GENESIS, network="mainnet")
# C-03 network confusion: client asks for mainnet, node is the test network (and the reverse)
case("C-03 client names 'mainnet', node is the test network", 101102, TESTNET_GENESIS, network="mainnet")
case("C-03b client names 'testnet', node is the main network", 101101, MAINNET_GENESIS, network="testnet")
# C-04 consistent spoof of the mainnet identity on an address that is no named network, with no network named
case("C-04 unnamed endpoint claiming the mainnet identity (no pin)", 101101, MAINNET_GENESIS, network=None)
# C-05 malformed identities
case("C-05 genesis with injected text", 101102, "<script>alert(1)</script>" + "0" * 39)
case("C-05b chain id far past 64 bits", 10 ** 40, TESTNET_GENESIS, rpc_chain_id="0x" + "f" * 40)
case("C-05c negative chain id", -101102, TESTNET_GENESIS)
case("C-05d chain id as text", "101102; DROP", TESTNET_GENESIS)
case("C-05e genesis missing", 101102, None)

# C-06 environment pins that disagree with each other
with Stub() as s:
    s.identity(101102, TESTNET_GENESIS)
    os.environ["VORDIUM_CHAIN_ID"] = "101102"
    os.environ["VORDIUM_GENESIS_SHA256"] = MAINNET_GENESIS
    try:
        net = N.resolve_network(rpc_url=s.base, timeout=3)
        ok, why = domain_built(net)
    except Exception as e:
        ok, why = False, f"{type(e).__name__}: {str(e)[:100]}"
    clean_env()
    R.check("C-06 VORDIUM_GENESIS_SHA256 disagrees with the node", not ok, why)

# C-07 the node changes its genesis after the client checked it (identity re-read)
with Stub() as s:
    s.identity(101102, TESTNET_GENESIS)
    vx = Vordex(rpc_url=s.base, network="testnet", specs=units.NO_RULES, chain_clock=None, timeout=3)
    s.routes[("POST", "/order/place")] = (200, {"status": "submitted"})
    try:
        vx.place_order(session_key=SESSION.key.hex(), owner=OWNER.address, pair_id=1, side=BUY, size="0.01",
                       price="1000", order_type=LIMIT, retries=1)
        first = True
    except Exception as e:
        first = False
    s.identity(101102, secrets.token_hex(32))
    vx.domain.ttl_s = 0          # read the identity again before the next signature (the default is 60 s)
    before = sum(1 for r in s.log if r["path"] == "/order/place")
    try:
        vx.place_order(session_key=SESSION.key.hex(), owner=OWNER.address, pair_id=1, side=BUY, size="0.01",
                       price="1000", order_type=LIMIT, retries=1)
        after_ok = True
        why = "signed after the node switched"
    except Exception as e:
        after_ok = False
        why = f"{type(e).__name__}: {str(e)[:100]}"
    sent = sum(1 for r in s.log if r["path"] == "/order/place") - before
    R.check("C-07 node switches genesis after the first order: next order refused", first and not after_ok and sent == 0,
            f"first={first}; {why}")

R.finish()
