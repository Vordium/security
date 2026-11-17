// C-24 (JavaScript SDK): the key never appears in an error, an inspected object, JSON or console output.
// Bad keys go to keySigner; a valid key signs orders against a hostile fake node; every error message, stack,
// util.inspect / JSON.stringify of the SDK's handles and everything written to the console is searched for the key.
// Run: node c12_keys_js.mjs   Exit: 0 defended, 1 the key leaked, 3 cannot run.
import { inspect } from 'node:util'
import { TESTNET_GENESIS, Results, fakeNet, SDK_VERSION } from './_kit.mjs'

let sdk, ethers
try { sdk = await import('@vordium/sdk'); ethers = await import('ethers') } catch (e) { console.log('cannot import: ' + e.message); process.exit(3) }
const R = new Results('C-24 key secrecy, JS SDK @vordium/sdk ' + SDK_VERSION)
const w = ethers.Wallet.createRandom()
const KEY = w.privateKey.slice(2)
const needles = [KEY, KEY.toUpperCase(), KEY.slice(0, 16), KEY.slice(-16), KEY.slice(20, 36)]
const leaks = (t) => needles.some((n) => String(t ?? '').includes(n) || String(t ?? '').toLowerCase().includes(n))
const texts = []
const captured = []
const orig = { log: console.log, error: console.error, warn: console.warn, info: console.info, debug: console.debug }
for (const k of Object.keys(orig)) console[k] = (...a) => { captured.push(a.map((x) => (typeof x === 'string' ? x : inspect(x, { depth: 6 }))).join(' ')) }

for (const bad of ['0x' + KEY.slice(0, -2), KEY + 'zz', '0x' + KEY + '00', KEY.slice(0, 32) + ' ' + KEY.slice(32), '0x' + KEY.replace(/a/g, 'g'), '0x' + '0'.repeat(64)]) {
  try { sdk.keySigner(bad) } catch (e) { texts.push(String(e.message), String(e.stack), inspect(e)) }
}
const net = fakeNet({ chainId: 101102, genesis: TESTNET_GENESIS })
net.handlers['POST /order/place'] = () => ({ status: 400, body: { error: 'bad', echo: 'x'.repeat(5000) }, retryAfter: null })
net.handlers['POST /order/cancel-all'] = () => { throw Object.assign(new Error('socket hang up'), { code: 'ECONNRESET' }) }
try {
  const c = await sdk.Vordium.connect({ network: net.preset('testnet'), transport: net, chainClock: false })
  const signer = sdk.keySigner(w.privateKey)
  const a = await c.account(signer, { sessionSigner: signer, specs: sdk.NO_RULES, nonce: new sdk.NonceAllocator(w.address, 'orders', sdk.memoryNonceStore()) })
  for (const f of [
    () => a.placeOrder({ pairId: 1, side: 'buy', size: '0.01', price: '1000', orderType: 'Limit' }),
    () => a.placeOrder({ pairId: 1, side: 'up', size: '0.01', price: '1000', orderType: 'Limit' }),
    () => a.cancelAll(0),
  ]) {
    try { texts.push(inspect(await f(), { depth: 8 })) } catch (e) { texts.push(String(e.message), String(e.stack), inspect(e, { depth: 8 })) }
  }
  texts.push(inspect(a, { depth: 4 }), inspect(c, { depth: 4 }), inspect(signer, { depth: 4 }))
  try { texts.push(JSON.stringify(a, (k, v) => (typeof v === 'bigint' ? v.toString() : v))) } catch (e) { texts.push(String(e.message)) }
} catch (e) { texts.push(String(e.stack)) }
for (const [k, f] of Object.entries(orig)) console[k] = f
const leaking = texts.filter(leaks)
R.check('C-24 no error, stack, inspected handle or answer carries the key (SDK objects)', leaking.length === 0, `${texts.length} texts; leaking: ${leaking.map((t) => t.slice(0, 60)).slice(0, 2).join(' | ')}`)
R.check('C-24b nothing the SDK printed to the console carries the key', !captured.some(leaks), `${captured.length} console lines`)
R.finish()
