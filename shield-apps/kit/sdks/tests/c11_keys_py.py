"""C-22..C-25 (Python SDK): key files and key secrecy.

C-22 a key file is created 0600 in one step, never overwritten, and not followed through a symlink planted at its path.
C-23 a key file that the group or other users can read is refused (0644, 0640, 0604).
C-24 the key never appears in: any error the SDK raises for a bad key, a bad key file, a hostile node's answers or a
     refused order; the repr/str of the SDK's objects; anything logged at DEBUG (including the HTTP library); stdout/stderr.
C-25 key-file read errors never echo the file's content.

Run:  python3 this file   (pip install vordium; no network access; uses a temporary folder)
Exit: 0 = defended, 1 = a key leaked or a bad mode was accepted, 3 = cannot run.
"""
import contextlib
import io
import logging
import os
import stat
import sys
import tempfile
import traceback
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kit import TESTNET_GENESIS, Results, Stub, clean_env  # noqa: E402

warnings.simplefilter("ignore")
clean_env()
try:
    import vordium
    from eth_account import Account
    from vordium import units, wallet
    from vordium.account_ops import AccountOps
    from vordium.dex import Vordex, BUY, LIMIT
    from vordium.mm import MarketMaker
except Exception as e:  # pragma: no cover
    print(f"cannot import vordium: {e}")
    sys.exit(3)

R = Results(f"C-22..C-25 key files and key secrecy, Python SDK vordium {vordium.__version__}")
acct = Account.create()
KEY = acct.key.hex().removeprefix("0x")
NEEDLES = [KEY, KEY.upper(), KEY[:16], KEY[-16:], KEY[20:36]]


def leaks(text: str) -> bool:
    t = text or ""
    return any(n in t or n in t.lower() for n in NEEDLES)


buf_log = io.StringIO()
h = logging.StreamHandler(buf_log)
h.setLevel(logging.DEBUG)
logging.getLogger().addHandler(h)
logging.getLogger().setLevel(logging.DEBUG)
out, err = io.StringIO(), io.StringIO()

with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    texts = []
    # C-22
    p = os.path.join(tmp, "k", "a.key")
    wallet.write_key_file(p, acct.address, "0x" + KEY)
    mode = stat.S_IMODE(os.stat(p).st_mode)
    dmode = stat.S_IMODE(os.stat(os.path.dirname(p)).st_mode)
    try:
        wallet.write_key_file(p, acct.address, "0x" + KEY)
        over = True
    except wallet.KeyFileError as e:
        over = False
        texts.append(str(e))
    victim = os.path.join(tmp, "victim.txt")
    open(victim, "w").write("victim\n")
    link = os.path.join(tmp, "k", "link.key")
    os.symlink(victim, link)
    try:
        wallet.write_key_file(link, acct.address, "0x" + KEY)
        followed = open(victim).read() != "victim\n"
    except Exception as e:
        followed = open(victim).read() != "victim\n"
        texts.append(str(e))
    r22 = (mode == 0o600, dmode == 0o700, not over, not followed)

    # C-23
    refused = {}
    for m in (0o644, 0o640, 0o604, 0o660):
        q = os.path.join(tmp, f"m{m:o}.key")
        wallet.write_key_file(q, acct.address, "0x" + KEY)
        os.chmod(q, m)
        try:
            wallet.read_key_file(q)
            refused[oct(m)] = False
        except wallet.KeyFileError as e:
            refused[oct(m)] = True
            texts.append(str(e))
    ok_read = wallet.read_key_file(p)[1] == "0x" + KEY

    # C-24 errors for bad keys and bad files
    bad_keys = ["0x" + KEY[:-2], KEY + "zz", "0x" + KEY + "00", KEY[:32] + " " + KEY[32:], "0x" + KEY.replace("a", "g")]
    for bk in bad_keys:
        for fn in (lambda k: wallet.Wallet.from_key(k), lambda k: AccountOps(k, identity=lambda: None),
                   lambda k: MarketMaker("http://127.0.0.1:9", k, acct.address, network="testnet")):
            try:
                fn(bk)
            except BaseException as e:
                texts.append(f"{e!r} {e}")
                texts.append("".join(traceback.format_exception_only(type(e), e)))
    for content in ('{"address": "x", "private_key": "' + KEY + '"', KEY + "\n", '["' + KEY + '"]'):
        q = os.path.join(tmp, f"bad{len(texts)}.key")
        fd = os.open(q, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, content.encode())
        os.close(fd)
        try:
            a, k = wallet.read_key_file(q)
            wallet.Wallet.from_key(k)
        except BaseException as e:
            texts.append(f"{e!r} {e}")
    # a hostile node: errors while placing an order with a valid key
    with Stub() as s:
        s.identity(101102, TESTNET_GENESIS)
        s.routes[("POST", "/order/place")] = (400, {"error": "bad", "echo": "x" * 5000})
        s.routes[("GET", "/markets/specs")] = ("raw", 200, b"{not json")
        for spec in (units.NO_RULES, None):
            try:
                vx = Vordex(rpc_url=s.base, network="testnet", specs=spec, chain_clock=None, timeout=2)
                res = vx.place_order(session_key="0x" + KEY, owner=acct.address, pair_id=1, side=BUY, size="0.01",
                                     price="1000", order_type=LIMIT, retries=1)
                texts.append(repr(res))
                texts.append(repr(vx) + str(vars(vx).get("domain")))
            except BaseException as e:
                texts.append(f"{e!r} {e}")
                texts.append("".join(traceback.format_exception(type(e), e, e.__traceback__)))
        mm = MarketMaker(s.base, "0x" + KEY, acct.address, network="testnet", chain_clock=None)
        try:
            texts.append(repr(mm.cancel_all(0)))
        except BaseException as e:
            texts.append(f"{e!r} {e}")
        texts.append(repr(mm) + str(mm))
    w = wallet.Wallet.from_key("0x" + KEY)
    texts += [repr(w), str(w), f"{w}", repr(Account.from_key("0x" + KEY))]

r24_texts = [t for t in texts if leaks(t)]
R.check("C-22 key file 0600, folder 0700, never overwritten, symlink at the path not followed", all(r22),
        f"mode {oct(mode)}, folder {oct(dmode)}, overwritten={not r22[2]}, symlink followed={not r22[3]}")
R.check("C-23 a key file others can read is refused (0644, 0640, 0604, 0660); 0600 is read",
        all(refused.values()) and ok_read, str(refused))
R.check("C-24 no error, repr or answer carries the key", not r24_texts,
        f"{len(texts)} texts checked; leaking: {[t[:80] for t in r24_texts][:3]}")
R.check("C-24b nothing logged at DEBUG, printed or written to stderr carries the key",
        not leaks(buf_log.getvalue()) and not leaks(out.getvalue()) and not leaks(err.getvalue()),
        f"{len(buf_log.getvalue())} log bytes")
R.check("C-25 key-file read errors never echo the content", not any(leaks(t) for t in texts if "key file" in t))
R.finish()
