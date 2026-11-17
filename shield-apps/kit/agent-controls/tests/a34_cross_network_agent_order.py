"""A34 - an agent order signed for the main network's domain is sent to the test network, and a test-network
signature is checked against the main network's domain. Expected: the test network refuses the main-network signature,
and the two networks' signatures differ for the same order (so neither network can take the other's).
--send-to-mainnet also sends the test-network signature once to the main network, which must refuse it."""
from shield import *
from vordium.network import use_network

run = Run("A34", "agent order signed for another network",
          extra=lambda p: p.add_argument("--send-to-mainnet", action="store_true", help="also send one POST the main network must refuse"))
net = Net(run)
s = setup_or_end(run, net)
eth = s["eth"]
p8 = near(net, eth)
size = net.size18(eth, "20", p8)
use_network("mainnet")                                      # sign under the main network's domain (reads only)
body_main = order_body(s["agent_key"], s["owner"], eth["pairId"], 0, size, p8, client_nonce=now_ms())
use_network("testnet")
r = post("/order/place", body_main)
run.step("mainnet_signed_to_testnet", http=r["http"], answer=r["answer"])
body_test = order_body(s["agent_key"], s["owner"], eth["pairId"], 0, size, p8, client_nonce=now_ms() + 1)
differ = body_main["signature"] != order_body(s["agent_key"], s["owner"], eth["pairId"], 0, size, p8,
                                              client_nonce=body_main["clientNonce"])["signature"]
run.step("signatures_differ_by_network", differ=differ)
rm_ans = (400, "not sent")
if run.args.send_to_mainnet:
    try:
        rm = requests.post("https://rpc.vordium.com/order/place", json=body_test, headers=UA, timeout=15)
        rm_ans = (rm.status_code, rm.json() if rm.headers.get("content-type", "").startswith("application/json") else rm.text[:200])
    except Exception as e:
        rm_ans = (None, type(e).__name__)
    run.step("testnet_signed_to_mainnet", answer=rm_ans)
code1 = (r["answer"] or {}).get("code") if isinstance(r["answer"], dict) else None
bad1 = intake_refused(r) and (code1 in ("bad_signature", "no_session") or "signature" in json.dumps(r["answer"]).lower())
bad2 = differ and isinstance(rm_ans[0], int) and rm_ans[0] >= 400
if not intake_refused(r):
    f = order_fate(s["owner"], s["agent"], body_main["clientNonce"], r, 8)
    if f["outcome"].startswith("accepted"):
        run.end(WORKS, "the test network took an order signed for the main network")
if bad1 and bad2:
    run.end(HOLDS, "the test network refused the main-network signature; the two domains give different signatures")
run.end(CANNOT, f"unclear answers: test {r['http']}, main {rm_ans[0]}")
