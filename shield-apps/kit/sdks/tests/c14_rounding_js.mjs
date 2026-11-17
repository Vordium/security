// C-26..C-28 (JavaScript SDK): rounding of sizes and prices, hostile inputs and hostile market rules.
// Run: node c14_rounding_js.mjs   (one public GET of the test network's market rules, else built-in rules)
// Exit: 0 defended, 1 a worse value was signed or a hostile input accepted, 3 cannot run.
import { TESTNET_GENESIS, Results, fakeNet, SDK_VERSION } from './_kit.mjs'

let sdk, ethers
try { sdk = await import('@vordium/sdk'); ethers = await import('ethers') } catch (e) { console.log('cannot import: ' + e.message); process.exit(3) }
const R = new Results('C-26..C-28 rounding and hostile values, JS SDK @vordium/sdk ' + SDK_VERSION)
let read
try { const r = await fetch('https://testnet.vordex.xyz/chain/markets/specs'); read = await r.json() } catch {
  console.log('[note] live market rules unreadable; using built-in rules')
  read = { specs: { min_order_notional_6dec: '10000000', pairs: [['10000000', '100000000000000'], ['10', '1000000000000000000'], ['1', '100000000000000000000']].map(([t, l], i) => ({ tick_8dec: t, lot_18dec: l, pair: { pair_id: i + 1, name: 'M' + i, active: true, min_size_18dec: '0', kind: 'perps' } })) } }
}
const specs = sdk.pairSpecs(read)
// exact decimal compare via scaled bigints: value * 10^k
const toUnits = (s, k) => { const [i, f = ''] = String(s).split('.'); return BigInt(i + (f + '0'.repeat(k)).slice(0, k)) + (f.length > k && /[1-9]/.test(f.slice(k)) ? 1n : 0n) }
const gcd = (a, b) => (b ? gcd(b, a % b) : a)
let n = 0
const bad = []
let seed = 438
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
const mags = ['0.00001234', '0.0027967', '1.5', '97.123456789', '3123.4567891', '64000.12345']
for (const [pid, sp] of specs) {
  const tick = BigInt(sp.tick8 ?? sp.tick_8dec ?? 1) || 1n
  const step = (tick * 100n) / gcd(tick, 100n)
  const lot = BigInt(sp.lot18 ?? sp.lot_18dec ?? 1) || 1n
  for (let i = 0; i < Math.floor(4000 / specs.size); i++) {
    const m = Number(mags[Math.floor(rnd() * mags.length)]) * (1 + (rnd() - 0.5))
    const p = m.toFixed(10).replace(/0+$/, '').replace(/\.$/, '')
    const s = (Math.floor(rnd() * 1e6) / 10 ** Math.floor(rnd() * 8) * 100).toFixed(8)
    for (const side of ['buy', 'sell']) {
      n++
      let p8
      try { p8 = sdk.price8OnTick(p, sp, side) } catch { continue }
      const floorU = BigInt(String(p).split('.')[0] + ((String(p).split('.')[1] ?? '') + '0'.repeat(8)).slice(0, 8))
      const ceilU = toUnits(p, 8)
      if ((side === 'buy' && p8 > floorU) || (side === 'sell' && p8 < ceilU) || p8 % step !== 0n) bad.push(['price', pid, side, p, String(p8)])
    }
    try {
      const s18 = sdk.size18OnLot(s, sp)
      if (s18 > toUnits(s, 18) || s18 % lot !== 0n) bad.push(['size', pid, s, String(s18)])
    } catch { /* refused */ }
  }
}
R.check(`C-26 ${n} prices and sizes on ${specs.size} markets: never worse than given, on the step`, bad.length === 0, `${bad.length} bad ${JSON.stringify(bad.slice(0, 2))}`)

const sp1 = specs.get(Math.min(...specs.keys()))
const accepted = []
for (const x of [NaN, Infinity, -1, '-0.5', '1e400', '', ' ', '1,5', '0x10', 'abc', true, null, undefined, [1], { a: 1 }, '1_000', '٣', '1٠5', '1５', 1e300]) {
  for (const f of [(v) => sdk.price8OnTick(v, sp1, 'buy'), (v) => sdk.size18OnLot(v, sp1)]) {
    try { accepted.push([String(x).slice(0, 10), String(f(x))]) } catch { /* refused */ }
  }
}
R.check('C-27j hostile inputs are refused before signing', accepted.length === 0, JSON.stringify(accepted.slice(0, 4)))

// C-28 hostile market rules from the node, through the full order path
const pid0 = Math.min(...specs.keys())
const w = ethers.Wallet.createRandom()
const worse = []
let sent = 0
for (const patch of [{ lot_18dec: '1' + '0'.repeat(60) }, { tick_8dec: '1' + '0'.repeat(30) }, { tick_8dec: '0' }, { tick_8dec: '-100' }, { tick_8dec: '1e2' }, { lot_18dec: '0' }]) {
  for (const side of ['buy', 'sell']) {
    const net = fakeNet({ chainId: 101102, genesis: TESTNET_GENESIS })
    const hs = JSON.parse(JSON.stringify(read))
    for (const p of hs.specs.pairs) if (Number(p.pair.pair_id) === pid0) Object.assign(p, patch)
    net.handlers['GET /markets/specs'] = () => ({ status: 200, body: hs })
    net.handlers['POST /order/place'] = (b) => {
      sent++
      const o = JSON.parse(b)
      const price8 = toUnits(String(o.price), 8), size18 = BigInt(o.size_18dec ?? o.size)
      if (size18 > toUnits('0.5', 18) || (side === 'buy' && price8 > toUnits('1000.123456789', 8)) || (side === 'sell' && price8 < toUnits('1000.12345678', 8))) worse.push([JSON.stringify(patch), side, o.price, String(size18)])
      return { status: 200, body: { status: 'submitted' }, retryAfter: null }
    }
    try {
      const c = await sdk.Vordium.connect({ network: net.preset('testnet'), transport: net, chainClock: false })
      const s = sdk.keySigner(w.privateKey)
      const a = await c.account(s, { nonce: new sdk.NonceAllocator(w.address, 'orders', sdk.memoryNonceStore()) })
      await a.placeOrder({ pairId: pid0, side, size: '0.5', price: '1000.123456789', orderType: 'Limit' })
    } catch { /* refused */ }
  }
}
R.check('C-28 hostile market rules never make a worse order', worse.length === 0, `${sent} orders sent under hostile rules; worse ${JSON.stringify(worse.slice(0, 2))}`)
R.finish()
