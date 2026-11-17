"""B11 - where the agent key lives. Expected: a key file other users can read is refused before the server starts
(also through a symlink); a passphrase file likewise; new-agent-key writes mode 600 and never overwrites; the OS
keychain is never read through a plaintext or failing backend; the HTTP server takes no key at all; error messages
name the path, never the key."""
from mcpkit import *
import tempfile, subprocess
from vordium_mcp import keys
from vordium_mcp.networks import ConfigError

run = Run("B11", "agent key storage and file modes")
d = Path(temp_dir("shield-keys-"))
key = os.urandom(32).hex()
loose = d / "loose.key"; loose.write_text(key); os.chmod(loose, 0o644)
tight = d / "tight.key"; tight.write_text(key); os.chmod(tight, 0o600)
link = d / "link.key"; link.symlink_to(loose)
pp = d / "pass.txt"; pp.write_text("pw"); os.chmod(pp, 0o644)
res = {}


def starts(*argv):
    try:
        config(*argv)
        return "started"
    except (ConfigError, SystemExit) as e:
        msg = str(e)
        return "refused" + (" (KEY IN MESSAGE)" if key in msg else "")


res["loose_file"] = starts("--allow-trading", "--owner", "0x" + "1" * 40, "--agent-key-file", str(loose))
res["symlink_to_loose"] = starts("--allow-trading", "--owner", "0x" + "1" * 40, "--agent-key-file", str(link))
res["tight_file"] = starts("--allow-trading", "--owner", "0x" + "1" * 40, "--agent-key-file", str(tight))
res["loose_passphrase"] = starts("--owner", "0x" + "1" * 40, "--agent-key-file", str(tight), "--agent-key-passphrase-file", str(pp))
res["http_with_key"] = starts("--http", "127.0.0.1:0", "--agent-key-file", str(tight))
res["http_with_trading"] = starts("--http", "127.0.0.1:0", "--allow-trading")
new = d / "sub" / "new.key"
from vordium_mcp.__main__ import new_agent_key
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc1 = new_agent_key(str(new))
mode = oct(os.stat(new).st_mode & 0o777)
before = new.read_text()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    rc2 = new_agent_key(str(new))
res["new_key_mode"] = mode
res["new_key_overwrite_refused"] = rc2 != 0 and new.read_text() == before
res["new_key_printed"] = before.strip()[-64:] in buf.getvalue()


class Plain:
    pass


class Fake:
    def __init__(self, backend):
        self.b = backend
        self.read = False

    def get_keyring(self):
        return self.b

    def get_password(self, *a):
        self.read = True
        return key


Plain.__module__ = "keyrings.alt.file"
Plain.__name__ = "PlaintextKeyring"
f = Fake(Plain())
res["plaintext_keychain_read"] = keys.keychain_get("testnet", "0x" + "1" * 40, kr=f) is not None or f.read
run.step("results", **res)
want = {"loose_file": "refused", "symlink_to_loose": "refused", "tight_file": "started", "loose_passphrase": "refused",
        "http_with_key": "refused", "http_with_trading": "refused", "new_key_mode": "0o600", "new_key_overwrite_refused": True,
        "new_key_printed": False, "plaintext_keychain_read": False}
wrong = {k: res[k] for k, v in want.items() if res[k] != v}
if wrong:
    run.end(WORKS, "key storage guard failed: " + json.dumps(wrong))
run.end(HOLDS, "loose files and links refused before start, HTTP takes no key, 600 and no overwrite, plaintext keychain never read")
