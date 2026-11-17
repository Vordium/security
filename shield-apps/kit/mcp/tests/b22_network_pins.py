"""B22 - which chain the server signs for. The server and the SDK each ship their networks' identity (chain id and
genesis) in the released package. A node, spec and network answer that all agree with EACH OTHER on another genesis
must still be refused: agreement among the network's own answers never replaces the shipped identity.
Expected: the server's pins equal the SDK's; the agreeing-but-different answers are named as off the pin."""
from mcpkit import *
from vordium_mcp import networks

run = Run("B22", "the shipped network identity wins over agreeing answers")
try:
    from vordium import pins as sdk_pins
except Exception:
    run.end(CANNOT, "the Vordium SDK is not installed (pip install \"vordium-mcp[trade]\")")
other = "ab" * 32
probs = networks.pin_problems("testnet", {"spec": 101102, "status": 101102, "truth": 101102},
                              {"spec": other, "status": other, "truth": other})
sdk = {}
for n in ("testnet", "mainnet"):
    try:
        p = sdk_pins.pin_for(n) if hasattr(sdk_pins, "pin_for") else sdk_pins.PINS[n]
        sdk[n] = (getattr(p, "chain_id", None) or p["chain_id"], getattr(p, "genesis_sha256", None) or p["genesis_sha256"])
    except Exception as e:
        sdk[n] = f"unreadable ({type(e).__name__})"
mine = {n: (networks.PINS[n]["chain_id"], networks.PINS[n]["genesis_sha256"]) for n in ("testnet", "mainnet")}
run.step("pins", server=mine, sdk=sdk, agreeing_other_genesis=probs)
if len(probs) != 3:
    run.end(WORKS, "answers that agree with each other on another genesis were not all refused")
if any(isinstance(v, str) for v in sdk.values()):
    run.end(CANNOT, "the SDK's pins could not be read: " + json.dumps(sdk))
if any(tuple(sdk[n]) != mine[n] for n in mine):
    run.end(WORKS, "the server's pins differ from the SDK's")
run.end(HOLDS, "the server's pins equal the SDK's; agreeing answers on another genesis are refused")
