// C-14..C-17 (JavaScript SDK): retry after a lost answer never signs a second body and never places a second order.
// A fake network records every copy (exact bytes) and does not deduplicate.
// Run: node c08_resend_js.mjs   Exit: 0 defended, 1 a second body signed / a second order applied, 3 cannot run.
import { TESTNET_GENESIS, Results, fakeNet, SDK_VERSION } from './_kit.mjs'

let sdk, ethers
try { sdk = await import('@vordium/sdk'); ethers = await import('ethers') } catch (e) { console.log('cannot import: ' + e.message); process.exit(3) }
const R = new Results('C-14..C-17 resend after a lost answer, JS SDK @vordium/sdk ' + SDK_VERSION)
const ownerW = ethers.Wallet.createRandom()
const owner = sdk.keySigner(ownerW.privateKey), session = sdk.keySigner(ethers.Wallet.createRandom().privateKey)

function chain(script) {
  const st = { copies: [], applied: new Map() }
  st.place = (body) => {
    st.copies.push(body)
    const step = script.length ? script.shift() : 'ok'
    const b = JSON.parse(body)
    const key = `${b.owner.toLowerCase()}:${b.clientNonce}`
    const first = !st.applied.has(key)
    if (step === 'ok' || step === 'lost') {
      if (!st.applied.has(key)) st.applied.set(key, [])
      st.applied.get(key).push( { id: 7, client_nonce: b.clientNonce, pair_id: b.pairId, side: b.side, size: b.size_18dec, price_8dec: String(Math.round(Number(b.price) * 1e8)), order_id: 7 })
    }
    if (step === '503') return { status: 503, body: { error: 'busy' }, retryAfter: null }
    if (step === 'lost') { const e = new Error('The operation was aborted due to timeout'); e.name = 'TimeoutError'; throw e }
    if (!first) return { status: 409, body: { code: 'nonce', error: 'nonce already used' }, retryAfter: null }
    return { status: 200, body: { status: 'submitted' }, retryAfter: null }
  }
  return st
}

async function client(net) {
  const c = await sdk.Vordium.connect({ network: net.preset('testnet'), transport: net, chainClock: false })
  return c.account(owner, { sessionSigner: session, specs: sdk.NO_RULES, nonce: new sdk.NonceAllocator(ownerW.address, 'orders', sdk.memoryNonceStore()) })
}
const order = (a) => a.placeOrder({ pairId: 1, side: 'buy', size: '0.01', price: '1000', orderType: 'Limit' })

// C-14
{
  const net = fakeNet({ chainId: 101102, genesis: TESTNET_GENESIS })
  const st = chain(['lost'])
  net.handlers['POST /order/place'] = st.place
  net.handlers[`GET /orders/${ownerW.address}`] = () => ({ status: 200, body: [...st.applied.values()].flat() })
  let res = {}, why
  try { res = await order(await client(net)); why = `alreadyReceived=${res.alreadyReceived} attempts=${res.attempts}` } catch (e) { why = `${e.name}: ${e.message.slice(0, 120)}` }
  R.check('C-14 lost answer: every copy is the same bytes', st.copies.length >= 2 && new Set(st.copies).size === 1, `${st.copies.length} copies, ${new Set(st.copies).size} distinct`)
  R.check('C-14b at most 3 copies, all under one client nonce', st.copies.length <= 3 && st.applied.size === 1, `${st.copies.length} copies, ${st.applied.size} distinct nonce(s); ${why}`)
  R.check("C-14c the answer is 'received' after a matching read-back", res.alreadyReceived === true, why)
}
// C-15
{
  const net = fakeNet({ chainId: 101102, genesis: TESTNET_GENESIS })
  const st = chain(['503', '503', 'ok'])
  net.handlers['POST /order/place'] = st.place
  let why
  try { const r = await order(await client(net)); why = `status=${r.status} attempts=${r.attempts}` } catch (e) { why = `${e.name}: ${e.message.slice(0, 120)}` }
  R.check('C-15 503, 503, 200: the same bytes each time', st.copies.length === 3 && new Set(st.copies).size === 1, `${st.copies.length} copies, ${new Set(st.copies).size} distinct; ${why}`)
}
// C-16 cancel-all is not deduplicated by the network: one copy after a lost answer
{
  const net = fakeNet({ chainId: 101102, genesis: TESTNET_GENESIS })
  const copies = []
  net.handlers['POST /order/cancel-all'] = (b) => { copies.push(b); const e = new Error('aborted'); e.name = 'TimeoutError'; throw e }
  let why
  try { const r = await (await client(net)).cancelAll(0); why = `submitted=${r.submitted} unknown=${r.unknown} refusal=${r.refusal?.code}` } catch (e) { why = `${e.name}: ${e.message.slice(0, 120)}` }
  R.check('C-16 cancel-all after a lost answer: one copy only, result unknown', copies.length === 1 && /unknown=true|delivery_unknown/.test(why), `${copies.length} copies; ${why}`)
}
// C-17 a new call takes a new nonce
{
  const net = fakeNet({ chainId: 101102, genesis: TESTNET_GENESIS })
  const st = chain(['503', '503', '503', 'ok'])
  net.handlers['POST /order/place'] = st.place
  const a = await client(net)
  try { await order(a) } catch { /* unknown */ }
  try { await order(a) } catch { /* */ }
  const n = st.copies.map((b) => JSON.parse(b).clientNonce)
  R.check('C-17 a new call takes a new nonce; old signed bytes never reused for it', n.length === 4 && new Set(n.slice(0, 3)).size === 1 && n[3] > n[0], `nonces ${n.join(',')}`)
}
R.finish()
