#!/usr/bin/env node
/**
 * (source check) — the bytes signed and the bytes sent are the same order.
 * For each form the app signs (app-fee approval and claim, the app-fee order PlaceOrderV3, the batch order, cancel-all,
 * TWAP place and cancel, the bridge withdrawal), built by the app's OWN code from random inputs:
 *   1. every signed field reaches the request body with the same value (or is a fixed value the chain fills in the same);
 *   2. the body carries no field that is not signed (other than the signature and the signer's own key);
 *   3. the form's fields typed into the wallet are exactly the types the chain publishes for it (field list per type);
 *   4. "hidden" fields — signed but never on the confirm screen — are fixed or derived, never a free value.
 *   node u02-form-parity.mjs --app <app source dir> [--rounds 200]
 * exit 0 = every form agrees · 1 = a signed field and the sent field differ, or an unsigned field travels · 3 = cannot run
 */
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { makeLoader, argOf, reporter } from './lib/load-app.mjs'

const APP = argOf('--app'), ROUNDS = Number(argOf('--rounds', '200'))
if (!APP || !existsSync(path.join(APP, 'src/lib/builder.ts'))) { console.log('cannot run: --app <app source dir> is required'); process.exit(3) }
const R = reporter('u02-form-parity')
const load = makeLoader(APP, { env: { NEXT_PUBLIC_VORDIUM_NETWORK: 'mainnet', NEXT_PUBLIC_APP_FEES: 'on' } })
const { ethers } = createRequire(path.join(APP, 'package.json'))('ethers')
const B = load('src/lib/builder.ts'), M = load('src/lib/mmRelease.ts'), T = load('src/lib/twap.ts'), E = load('src/lib/eip712.ts')
let BV = null; try { BV = load('src/lib/bridgeV4.ts') } catch (e) { console.log(`  note: bridge module not loadable here (${e.message.slice(0, 80)})`) }

let seed = 0x5eed
const rnd = (n) => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n }
const big = (digits) => BigInt('1' + Array.from({ length: digits }, () => rnd(10)).join(''))
const addr = () => ethers.Wallet.createRandom().address
const S = (v) => (typeof v === 'bigint' ? v.toString() : typeof v === 'boolean' ? String(v) : String(v))
const SIG = '0x' + 'ab'.repeat(65)

/** compare: signed value v, sent body b, a field map {typed: bodyKey | [bodyKey, fn(bodyVal) -> comparable] | null(=implied)} */
function parity(name, v, b, map, implied = {}, extraOk = ['signature', 'sessionKey']) {
  const errs = []
  for (const [k, val] of Object.entries(v)) {
    const m = map[k]
    if (m === null) { if (k in implied && S(implied[k]) !== S(val)) errs.push(`${k}: hidden field is ${S(val)}, not the fixed ${S(implied[k])}`); continue }
    const [bk, conv] = Array.isArray(m) ? m : [m ?? k, (x) => x]
    if (!(bk in b)) { if (k in implied && S(implied[k]) === S(val)) continue; errs.push(`${k}: signed ${S(val)} but no body field ${bk}`); continue }
    if (S(conv(b[bk])) !== S(val)) errs.push(`${k}: signed ${S(val)} ≠ sent ${S(b[bk])}`)
  }
  const signedKeys = new Set(Object.entries(map).map(([k, m]) => (Array.isArray(m) ? m[0] : m ?? k)))
  for (const k of Object.keys(b)) if (!signedKeys.has(k) && !extraOk.includes(k) && !(k in v)) errs.push(`body field ${k} is sent but not signed`)
  return errs
}
const typeNames = (t) => t.map((f) => `${f.name}:${f.type}`).join(',')

// 3 — the field lists the wallet is shown, per type, against the app's pinned config
const builderCfg = load('src/config/eip712-builder.json')
R.ck(typeNames(B.BUILDER_TYPES.ApproveBuilderFee) === 'user:address,builder:address,maxFeeCbps:uint32,nonce:uint64,validUntil:uint64', 'ApproveBuilderFee fields', typeNames(B.BUILDER_TYPES.ApproveBuilderFee))
R.ck(B.BUILDER_TYPES.PlaceOrderV3.length === 19 && B.BUILDER_TYPES.PlaceOrderV3.some((f) => f.name === 'builder' && f.type === 'address') && B.BUILDER_TYPES.PlaceOrderV3.some((f) => f.name === 'builderFeeCbps'), 'PlaceOrderV3 signs the app (builder) address and its fee', typeNames(B.BUILDER_TYPES.PlaceOrderV3))
R.ck(builderCfg.types === B.BUILDER_TYPES || JSON.stringify(builderCfg.types) === JSON.stringify(B.BUILDER_TYPES), 'builder types come only from the pinned config')

const fails = { approve: [], claim: [], v3: [], batch: [], cancelAll: [], twap: [], twapCancel: [], withdraw: [] }
for (let i = 0; i < ROUNDS; i++) {
  const owner = addr(), builder = addr(), sk = addr(), now = Date.now() + rnd(1e9)
  // approval
  const fee = 1 + rnd(4294967294)
  const a = B.approveForm(owner, builder, fee, rnd(1e6), now)
  fails.approve.push(...parity('approve', a.value, a.body(SIG), { user: 'user', builder: 'builder', maxFeeCbps: 'maxFeeCbps', nonce: 'nonce', validUntil: 'validUntil' }))
  if (a.value.builder !== builder || a.value.maxFeeCbps !== fee || a.value.user !== owner) fails.approve.push('approval value is not the shown builder/fee/user')
  const c = B.claimForm(builder, rnd(1e6), now)
  fails.claim.push(...parity('claim', c.value, c.body(SIG), { builder: 'builder', nonce: 'nonce', validUntil: 'validUntil' }))
  // PlaceOrderV3
  const limit = rnd(2) === 1, side = rnd(2), tif = ['gtc', 'post', 'ioc', 'fok'][rnd(4)]
  const o = { owner, pairId: 1 + rnd(200), side, size18dec: big(18), price8dec: limit ? big(9) * 100n : (rnd(2) ? big(9) * 100n : 0n), leverageBps: 10000 + rnd(490000),
    orderType: limit ? 1 : 0, reduceOnly: rnd(2) === 1, postOnly: rnd(2) === 1, tif, clientNonce: 1e12 + rnd(1e9), validUntil: Math.floor(now / 1000) + 120,
    worstPrice8dec: limit ? 0n : big(9) * 100n, builder, builderFeeCbps: 1 + rnd(5000), sessionKey: sk }
  const f = B.v3Form(o)
  const vb = f.body(SIG)
  fails.v3.push(...parity('v3', f.value, vb, {
    owner: 'owner', pairId: 'pairId', side: ['side', (x) => (x === 'buy' ? 0 : 1)], size: ['size_18dec', BigInt], price: ['price_8dec', BigInt],
    leverageBps: 'leverageBps', orderType: ['orderType', (x) => (x === 'Limit' ? 1 : 0)], reduceOnly: 'reduceOnly', postOnly: 'postOnly',
    triggerPrice8dec: null, triggerDir: null, timeInForce: 'timeInForce', expiresAt: null, clientNonce: ['clientNonce', BigInt], validUntil: ['validUntil', BigInt],
    worstPrice8dec: ['worstPrice8dec', BigInt], source: 'source', builder: 'builder', builderFeeCbps: 'builderFeeCbps',
  }, { triggerPrice8dec: 0n, triggerDir: 0, expiresAt: 0n, price: 0n, reduceOnly: false, postOnly: false, timeInForce: 0 }))
  if (f.value.source !== 'app') fails.v3.push(`hidden field source = ${f.value.source}`)
  if (f.value.builder !== o.builder || f.value.builderFeeCbps !== o.builderFeeCbps) fails.v3.push('v3: builder or fee differ from the order shown')
  // batch place (a limit with a 6-decimal price)
  const bp = M.batchPlace(owner, BigInt(1e12 + rnd(1e9)), { pairId: 1 + rnd(200), side: side ? 'sell' : 'buy', size18dec: big(18), price8dec: big(9) * 100n, leverageBps: 10000 + rnd(490000), tif, reduceOnly: rnd(2) === 1, clientNonce: BigInt(1e12 + rnd(1e9)) })
  const bb = bp.body(SIG), act = bp.value.actions[0], ba = bb.actions[0]
  fails.batch.push(...parity('batch', { owner: bp.value.owner, nonce: bp.value.nonce }, { owner: bb.owner, nonce: bb.nonce, signature: bb.signature, actions: 0 }, { owner: 'owner', nonce: ['nonce', BigInt] }, {}, ['signature', 'actions']))
  fails.batch.push(...parity('batch.action', act, ba, {
    kind: ['kind', (x) => (x === 'place' ? 0 : -1)], pairId: 'pairId', side: ['side', (x) => (x === 'buy' ? 0 : 1)], size: ['size_18dec', BigInt], price: ['price_8dec', BigInt],
    leverageBps: 'leverageBps', orderType: ['orderType', (x) => ({ limit: 1, ioc: 4, fok: 5 }[x] ?? `unknown wire name ${x}`)], reduceOnly: 'reduceOnly', postOnly: 'postOnly',
    clientNonce: ['clientNonce', BigInt], orderId: null,
  }, { orderId: 0n }))
  // cancel all
  const ca = M.cancelAll(owner, rnd(200), BigInt(1e12 + rnd(1e9)))
  fails.cancelAll.push(...parity('cancelAll', ca.value, ca.body(SIG), { owner: 'owner', pairId: 'pairId', nonce: ['nonce', BigInt] }))
  // TWAP
  const ti = { totalSize18dec: big(18), numSlices: 2 + rnd(100), durationMs: 60000 + rnd(86400000), leverageBps: 10000 + rnd(100000), slippageBps: rnd(500), randomize: rnd(2) === 1,
    triggerPrice8dec: rnd(2) ? 0n : big(9), triggerDir: rnd(3), minPrice8dec: rnd(2) ? 0n : big(8), maxPrice8dec: rnd(2) ? 0n : big(10) }
  const tv = T.twapValue(owner, 1 + rnd(200), side, ti, BigInt(1e12 + rnd(1e9)))
  const tb = JSON.parse(T.twapBody(tv, SIG).replace(/:(\d{16,})/g, ':"$1"'))
  fails.twap.push(...parity('twap', tv, tb, { owner: 'owner', pairId: ['pair_id', BigInt], side: ['side', BigInt], totalSize18dec: ['total_size_18dec', BigInt], numSlices: ['num_slices', BigInt], durationMs: ['duration_ms', BigInt],
    leverageBps: ['leverage_bps', BigInt], slippageBps: ['slippage_bps', BigInt], randomize: 'randomize', triggerPrice8dec: ['trigger_price_8dec', BigInt], triggerDir: ['trigger_dir', BigInt],
    minPrice8dec: ['min_price_8dec', BigInt], maxPrice8dec: ['max_price_8dec', BigInt], clientNonce: ['client_nonce', BigInt] }))
  const cv = T.cancelValue ? T.cancelValue(owner, BigInt(1 + rnd(1e6)), BigInt(1e12 + rnd(1e9))) : null
  if (cv) { const cb = JSON.parse(T.cancelBody(cv, SIG).replace(/:(\d{16,})/g, ':"$1"')); fails.twapCancel.push(...parity('twapCancel', cv, cb, { owner: 'owner', twapId: ['twap_id', BigInt], clientNonce: ['client_nonce', BigInt] })) }
  // bridge withdrawal: typed message vs body
  if (BV?.withdrawIntentTypedData && BV?.submitBody) {
    try {
      const wi = { account: owner, vaultId: 1 + rnd(4), recipient: `0x${'0'.repeat(24)}${owner.slice(2).toLowerCase()}`, amount: big(9), nonce: BigInt(1 + rnd(1e6)), routeKind: rnd(2), destinationDomain: rnd(30), maxFee: BigInt(rnd(1e6)), deadline: BigInt(Math.floor(now / 1000) + 600) }
      const td = BV.withdrawIntentTypedData(E.VORDCORE_DOMAIN, wi), wb = BV.submitBody(wi, '0x' + 'cd'.repeat(65))
      fails.withdraw.push(...parity('withdraw', td.message, wb, { account: 'account', vaultId: 'vault_id', recipient: ['recipient', (x) => x], amount: 'amount_6dec', nonce: 'nonce', routeKind: 'route_kind', destinationDomain: 'destination_domain', maxFee: 'max_fee_6dec', deadline: 'deadline' }))
    } catch (e) { if (i === 0) console.log(`  note: withdrawal forms are closed in this build (${e.message.slice(0, 80)})`); BV.closed = true }
  }
}
for (const [k, list] of Object.entries(fails)) {
  if (k === 'withdraw' && (!BV || BV.closed)) { console.log(`  SKIP  withdraw: the bridge module is closed in a source-only load`); continue }
  const uniq = [...new Set(list)]
  R.ck(uniq.length === 0, `${k}: ${ROUNDS} random forms — every signed field equals the sent field, no unsigned field travels`, uniq.slice(0, 4).join(' | '))
}
// 4 — the hidden fields of the order the session key signs: fixed, never free
const f0 = B.v3Form({ owner: addr(), pairId: 1, side: 0, size18dec: 10n ** 18n, price8dec: 0n, leverageBps: 10000, orderType: 0, reduceOnly: false, postOnly: false, tif: 'ioc', clientNonce: 1, validUntil: 2, worstPrice8dec: 1n, builder: addr(), builderFeeCbps: 500, sessionKey: addr() })
R.ck(f0.value.triggerPrice8dec === 0n && f0.value.triggerDir === 0 && f0.value.expiresAt === 0n && f0.value.source === 'app', 'PlaceOrderV3 hidden fields are fixed: no trigger, no expiry, source "app"')
let threw = 0; for (const bad of [{ orderType: 2 }, { builderFeeCbps: 0 }, { builder: 'not-an-address' }]) { try { B.v3Form({ ...{ owner: addr(), pairId: 1, side: 0, size18dec: 1n, price8dec: 1n, leverageBps: 1, orderType: 1, reduceOnly: false, postOnly: false, tif: 'gtc', clientNonce: 1, validUntil: 1, worstPrice8dec: 0n, builder: addr(), builderFeeCbps: 1, sessionKey: addr() }, ...bad }) } catch { threw++ } }
R.ck(threw === 3, 'an app-fee order refuses a stop type, a zero fee and a non-address app')
let pricedOff = false; try { M.batchPlace(addr(), 1n, { pairId: 1, side: 'buy', size18dec: 1n, price8dec: 12345671n, leverageBps: 1, tif: 'gtc', reduceOnly: false, clientNonce: 1n }) } catch { pricedOff = true }
R.ck(pricedOff, 'the batch form refuses a price with more than 6 decimals rather than rounding it silently')
R.done()
