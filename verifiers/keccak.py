"""keccak-256 (the original Keccak padding 0x01, as Ethereum uses; not SHA3-256), pure Python, standard library only.
Used by every verifier here so they run with a plain Python 3.9+ and nothing to install.
Self-test: python3 keccak.py  (known vectors)."""

_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
       0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
       0x000000000000800A, 0x800000008000000A, 0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14]
_M = (1 << 64) - 1


def _rotl(x, n):
    return ((x << n) | (x >> (64 - n))) & _M if n else x


def _f(s):
    for rc in _RC:
        c = [s[x] ^ s[x + 5] ^ s[x + 10] ^ s[x + 15] ^ s[x + 20] for x in range(5)]
        for x in range(5):
            d = c[(x + 4) % 5] ^ _rotl(c[(x + 1) % 5], 1)
            for y in range(0, 25, 5):
                s[x + y] ^= d
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rotl(s[x + 5 * y], _ROT[x + 5 * y])
        for x in range(5):
            for y in range(0, 25, 5):
                s[x + y] = b[x + y] ^ (~b[(x + 1) % 5 + y] & _M & b[(x + 2) % 5 + y])
        s[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    p = bytearray(data)
    p += b"\x00" * (rate - len(p) % rate)
    p[len(data)] ^= 0x01
    p[-1] ^= 0x80
    s = [0] * 25
    for o in range(0, len(p), rate):
        for i in range(rate // 8):
            s[i] ^= int.from_bytes(p[o + 8 * i:o + 8 * i + 8], "little")
        _f(s)
    return b"".join(s[i].to_bytes(8, "little") for i in range(4))


if __name__ == "__main__":
    V = [(b"", "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
         (b"abc", "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")]
    bad = [m for m, h in V if keccak256(m).hex() != h]
    print("keccak self-test:", "PASS" if not bad else f"FAIL {bad}")
    raise SystemExit(1 if bad else 0)
