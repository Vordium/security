"""Shared helpers for the Vordium re-run kit: polite public reads (no keys, no accounts) and a pure-Python Keccak-256.
Standard library only (Python 3.9+)."""
import json, time, urllib.parse, urllib.request

UA = "vordium-rerun-kit/1"


class Reader:
    """GET JSON from public routes, at most `rate` requests a second, with a few retries on errors and 429/5xx."""

    def __init__(self, rate=4.0, timeout=30, retries=3):
        self.gap, self.timeout, self.retries, self.last, self.count = 1.0 / rate, timeout, retries, 0.0, 0

    def get(self, base, path, keep_404=False, **params):
        """JSON answer, or None on 404 (with keep_404: the 404's own JSON body, e.g. {"error": "no leaf …"})."""
        q = {k: v for k, v in params.items() if v is not None}
        url = base.rstrip("/") + path + ("?" + urllib.parse.urlencode(q) if q else "")
        err = None
        for i in range(self.retries + 1):
            wait = self.last + self.gap - time.monotonic()
            if wait > 0: time.sleep(wait)
            self.last = time.monotonic(); self.count += 1
            try:
                req = urllib.request.Request(url, headers={"user-agent": UA, "accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                err = e
                if e.code == 404:
                    if keep_404:
                        try: return json.loads(e.read().decode())
                        except (ValueError, OSError): return None
                    return None
                if e.code not in (429, 500, 502, 503, 504): raise
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                err = e
            time.sleep(min(2 ** i, 8))
        raise RuntimeError(f"no answer from {url}: {err}")


# ---- Keccak-256 (the original Keccak padding 0x01, as Ethereum uses; NOT hashlib.sha3_256) --------------------------------
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
       0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
       0x000000000000800A, 0x800000008000000A, 0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _f(a):
    for rc in _RC:
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ (((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & _M) for x in range(5)]
        a = [[a[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                r = _ROT[x][y]
                b[y][(2 * x + 3 * y) % 5] = ((a[x][y] << r) | (a[x][y] >> (64 - r))) & _M if r else a[x][y]
        a = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        a[0][0] ^= rc
    return a


def keccak256(data: bytes) -> bytes:
    rate = 136
    p = bytearray(data) + b"\x01" + b"\x00" * ((-len(data) - 1) % rate)
    p[-1] |= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(p), rate):
        blk = p[off:off + rate]
        for i in range(rate // 8):
            x, y = i % 5, i // 5
            a[x][y] ^= int.from_bytes(blk[8 * i:8 * i + 8], "little")
        a = _f(a)
    out = b"".join(a[i % 5][i // 5].to_bytes(8, "little") for i in range(4))
    return out


assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
