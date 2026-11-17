"""B10 - a prompt-injected client smuggles key material through a tool argument (a private key, a recovery phrase, a
key in a field named like a secret, nested). Expected: refused before anything is read or sent, and the value never
appears in the answer. A transaction hash in a hash argument (same shape as a key) is still accepted."""
from mcpkit import *
from eth_account import Account

run = Run("B10", "key material passed through tool arguments")
cfg = config()
rec = Recorder()
chain = make(cfg, rec)
k = "0x" + os.urandom(32).hex()
Account.enable_unaudited_hdwallet_features()
phrase = Account.create_with_mnemonic()[1]
CASES = [("get_orderbook", {"symbol": k}), ("get_orderbook", {"symbol": k[2:]}), ("get_balance", {"address": phrase}),
         ("get_orderbook", {"symbol": "ETH", "private_key": "x"}), ("get_orderbook", {"symbol": "ETH", "nested": {"seed": "x"}}),
         ("get_orderbook", {"symbol": "ETH", "list": [k]}), ("get_points", {"address": phrase.upper()})]
leaks, taken = [], []
for name, args in CASES:
    n0 = len(rec.calls)
    res = call_tool(chain, cfg, name, args)
    text = json.dumps(res["raw"])
    if k[2:] in text or phrase in text or phrase.upper() in text:
        leaks.append(name)
    if not res["is_error"] or len(rec.calls) != n0:
        taken.append((name, list(args)))
    run.step("case", tool=name, fields=list(args), refused=res["is_error"], reads=len(rec.calls) - n0)
ok_hash = call_tool(chain, cfg, "get_tx", {"hash": "0x" + os.urandom(32).hex()})
hash_refused_as_key = "looks like a private key" in json.dumps(ok_hash["raw"])
run.step("tx_hash", refused_as_key=hash_refused_as_key)
if leaks or taken:
    run.end(WORKS, f"echoed {leaks}; not refused before reading {taken}")
if hash_refused_as_key:
    run.end(WORKS, "a transaction hash was refused as a key (a usability break, not a leak)")
run.end(HOLDS, f"{len(CASES)} key-shaped arguments refused before any read, never echoed; a transaction hash still works")
