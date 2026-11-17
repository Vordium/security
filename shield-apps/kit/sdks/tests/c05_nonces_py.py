"""C-10..C-13 (Python SDK): the client-nonce allocator under concurrency, a crash and a clock set back.

C-10 6 processes x 4 threads take 150 nonces each for ONE account from one state folder: every nonce is unique and
     each thread's nonces strictly rise (a duplicate would let a second order collide with, or replay, the first).
C-11 a process is killed (SIGKILL) while it takes nonces; a new process's first nonce is above every one handed out.
C-12 the computer's clock goes back one hour: nonces still rise (the mark, not the clock, decides).
C-13 the state folder is 0700 and every mark file 0600.

Run:  python3 this file      (pip install vordium; no network access; uses a temporary folder)
Exit: 0 = defended, 1 = a nonce repeated or went back, 3 = cannot run.
"""
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ACCOUNT = "0x" + "ab" * 20


def child(state: str, n: int, threads: int, tag: str) -> None:
    from vordium import nonces
    out, lock = [], threading.Lock()

    def run(t):
        a = nonces.NonceAllocator(ACCOUNT, nonces.ORDERS, state=state)
        for _ in range(n):
            v = a()
            with lock:
                sys.stdout.write(f"{tag}{t} {v}\n")
                sys.stdout.flush()
    ts = [threading.Thread(target=run, args=(i,)) for i in range(threads)]
    [t.start() for t in ts]
    [t.join() for t in ts]


if len(sys.argv) > 1 and sys.argv[1] == "--child":
    child(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
    sys.exit(0)

from _kit import Results  # noqa: E402
try:
    import vordium
    from vordium import nonces
except Exception as e:  # pragma: no cover
    print(f"cannot import vordium: {e}")
    sys.exit(3)

R = Results(f"C-10..C-13 nonce allocator, Python SDK vordium {vordium.__version__}")
me = os.path.abspath(__file__)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

with tempfile.TemporaryDirectory() as tmp:
    state = os.path.join(tmp, "nonces")
    # C-10
    procs = [subprocess.Popen([sys.executable, me, "--child", state, "150", "4", f"p{i}t"], stdout=subprocess.PIPE,
                              text=True, env=env) for i in range(6)]
    rows = []
    for p in procs:
        o, _ = p.communicate(timeout=240)
        rows += [ln.split() for ln in o.splitlines() if ln.strip()]
    vals = [int(v) for _, v in rows]
    seqs = {}
    for k, v in rows:
        seqs.setdefault(k, []).append(int(v))
    rising = all(all(b > a for a, b in zip(s, s[1:])) for s in seqs.values())
    R.check("C-10 24 workers x 150 nonces: all unique", len(vals) == 3600 and len(set(vals)) == len(vals),
            f"{len(vals)} taken, {len(set(vals))} distinct")
    R.check("C-10b each worker's nonces strictly rise", rising, f"{len(seqs)} workers")
    top = max(vals)

    # C-11 crash
    p = subprocess.Popen([sys.executable, me, "--child", state, "100000", "2", "k"], stdout=subprocess.PIPE, text=True,
                         env=env)
    seen = []
    t_end = time.time() + 1.5
    while time.time() < t_end:
        ln = p.stdout.readline()
        if ln.strip():
            seen.append(int(ln.split()[1]))
    os.kill(p.pid, signal.SIGKILL)
    p.wait(timeout=10)
    rest = p.stdout.read()
    seen += [int(x.split()[1]) for x in rest.splitlines() if x.strip()]
    after = nonces.NonceAllocator(ACCOUNT, nonces.ORDERS, state=state)()
    R.check("C-11 after SIGKILL, the next nonce is above every one handed out", seen and after > max(seen + [top]),
            f"killed after {len(seen)} nonces; next {after} > {max(seen + [top])}")

    # C-12 clock set back one hour
    t = [time.time()]
    a = nonces.NonceAllocator(ACCOUNT, nonces.ORDERS, state=state, clock=lambda: t[0])
    n1 = a()
    t[0] -= 3600
    n2 = a()
    n3 = a()
    R.check("C-12 clock back one hour: nonces still rise", n1 < n2 < n3, f"{n1} < {n2} < {n3}")

    # C-13 modes
    dmode = stat.S_IMODE(os.stat(state).st_mode)
    fmodes = {f: stat.S_IMODE(os.stat(os.path.join(state, f)).st_mode) for f in os.listdir(state)}
    bad = {f: oct(m) for f, m in fmodes.items() if m & 0o077}
    R.check("C-13 state folder 0700, mark files 0600", dmode == 0o700 and not bad,
            f"folder {oct(dmode)}; files {sorted(set(oct(m) for m in fmodes.values()))}")
R.finish()
