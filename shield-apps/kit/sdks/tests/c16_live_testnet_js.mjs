// C-30 (JavaScript SDK, LIVE test network): the chain accepts the SDK's signatures, op by op.
// A fresh throwaway account (never funded; keys only in memory, never printed) signs with the SDK's normal API:
// SessionCreate, PlaceOrder (judged on the balance, not the signature), RegisterAgentV2 + RevokeAgent (account-key ops,
// 65-byte signatures, read back from the chain), ApproveBuilderFee + its revoke (builder fee approval), SessionRevoke.
// Run: node c16_live_testnet_js.mjs   Exit: 0 every signature accepted as made, 1 the chain refused one, 3 cannot run.
import { Results, SDK_VERSION } from './_kit.mjs'

let sdk, ethers
try { sdk = await import('@vordium/sdk'); ethers = await import('ethers') } catch (e) { console.log('cannot import: ' + e.message); process.exit(3) }
const R = new Results('C-30 live test network accepts the SDK\'s signatures, JS SDK @vordium/sdk ' + SDK_VERSION)
const SIG = /signature|bad_sig|recover/i
let c
try { c = await sdk.Vordium.connect({ network: 'testnet' }) } catch (e) { console.log('cannot reach the test network: ' + e.message); process.exit(3) }
const ow = ethers.Wallet.createRandom(), sw = ethers.Wallet.createRandom(), aw = ethers.Wallet.createRandom()
console.log(`throwaway owner ${ow.address.slice(0, 10)}…  session ${sw.address.slice(0, 10)}…  chain ${c.network.chainId}`)
const store = sdk.memoryNonceStore()
const a = await c.account(sdk.keySigner(ow.privateKey), { sessionSigner: sdk.keySigner(sw.privateKey), nonce: new sdk.NonceAllocator(ow.address, 'orders', store) })
const show = (x) => JSON.stringify(x, (k, v) => (typeof v === 'bigint' ? v.toString() : v)).slice(0, 220)

let r = await a.createSession(sw.address, Date.now() + 20 * 60_000)
console.log('  session: ' + show(r))
R.check('C-30a SessionCreate applied (confirmed on the chain)', r.applied === true)
if (r.applied === true) {
  const o = await a.placeOrder({ pairId: 1, side: 'buy', size: '0.01', price: '1000', orderType: 'Limit' })
  console.log('  order: ' + show({ status: o.status, refusal: o.refusal, submitted: o.submitted }))
  R.check('C-30b PlaceOrder: judged on the account, not on the signature', !(o.status >= 400 && SIG.test(show(o.refusal))), `HTTP ${o.status} ${o.refusal?.code ?? ''}`)
  try {
    r = await a.registerAgent({ agent: aw.address, name: 'kit agent', mandate: 'test', expiresMs: Date.now() + 3_600_000 })
    console.log('  register agent: ' + show(r))
    R.check('C-30i RegisterAgentV2 (owner, 65-byte signature) applied', r.applied === true)
    if (r.applied === true) {
      r = await a.revokeAgent(aw.address)
      console.log('  revoke agent: ' + show(r))
      R.check('C-30j RevokeAgent applied', r.applied === true)
    }
  } catch (e) { R.check('C-30i RegisterAgentV2 / RevokeAgent', false, e.message.slice(0, 150)) }
  try {
    const builder = ethers.Wallet.createRandom().address
    r = await a.approveBuilderFee(builder, 10)
    console.log('  approve builder fee: ' + show(r))
    R.check('C-30k ApproveBuilderFee: not refused for its signature', r.applied === true || !SIG.test(show(r)), show(r).slice(0, 120))
    if (r.applied === true) {
      r = await a.revokeBuilderFee(builder)
      R.check('C-30l builder fee approval revoked', r.applied === true || !SIG.test(show(r)), show(r).slice(0, 120))
    }
  } catch (e) { R.check('C-30k ApproveBuilderFee', !SIG.test(e.message), e.message.slice(0, 150)) }
  r = await a.revokeSession()
  console.log('  revoke session: ' + show(r))
  R.check('C-30h SessionRevoke applied', r.applied === true)
}
R.finish()
