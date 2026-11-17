"""B09 - freezing the server with one argument. The key-material guard runs on every call, before anything else; a
regular expression with nested repetition would hang on a long run of letters. Expected: a 4,096-letter argument,
letter-and-space runs, and a mnemonic-shaped run each answer in under 2 seconds; anything longer than 4,096
characters is refused at once."""
from mcpkit import *

run = Run("B09", "denial of service through one long argument")
cfg = config()
chain = make(cfg, lambda m, u, b=None, timeout=12: (200, json.dumps({"pairs": [], "chain_time_ms": 1})))
PAY = {"letters_4096": "a" * 4096, "LETTERS_4096": "A" * 4096, "words_4096": ("abcd " * 820)[:4096],
       "mixed_4096": ("abc" * 1400)[:4095] + "!", "twelve_words_plus": "abandon " * 11 + "a" * 3000, "over_4096": "a" * 60000}
worst, rows = 0.0, {}
for k, v in PAY.items():
    t0 = time.time()
    res = call_tool(chain, cfg, "get_orderbook", {"symbol": v})
    dt = time.time() - t0
    worst = max(worst, dt)
    rows[k] = {"seconds": round(dt, 3), "refused": res["is_error"], "reason": (res["structured"] or {}).get("reason", "")[:100]}
    run.step("payload", name=k, **rows[k])
if worst > 2.0:
    run.end(WORKS, f"one argument held the server for {worst:.1f} s")
if not rows["over_4096"]["refused"]:
    run.end(WORKS, "an argument over 4,096 characters was not refused")
run.end(HOLDS, f"slowest answer {worst:.3f} s; over 4,096 characters refused")
