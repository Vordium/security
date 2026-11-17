#!/usr/bin/env node
/**
 * (live, test network) — the AI relay sign-in (EIP-4361 text + a device key) seen from a look-alike site.
 * A phishing page cannot get a sign-in for its own domain accepted, cannot redeem a captured text with its own device key,
 * cannot replay a nonce or a request proof, and a stolen device token is useless without the device key. Every account and
 * key here is made fresh for the run (never funded). The one accepted sign-in is the control (the "victim" signing in on
 * the real page); the residual a wallet warning must stop — a clone that gets the victim to sign the correct text for the
 * clone's own key — is recorded with what that sign-in can NOT do and how one signature ends it.
 *   node r01-relay-signin.mjs [--relay https://mcp.vordium.com/testnet] [--app https://testnet.vordex.xyz] [--out DIR]
 * exit 0 = every attack refused · 1 = an attack works · 3 = cannot run
 */
import { createRequire } from 'node:module'
import { createHash, generateKeyPairSync, randomBytes, sign as edsign } from 'node:crypto'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d }
const RELAY = arg('--relay', 'https://mcp.vordium.com/testnet').replace(/\/+$/, ''), APP = arg('--app', 'https://testnet.vordex.xyz'), OUT = arg('--out')
const HOST = new URL(APP).host
const DEPS = [HERE, ...String(arg('--deps', '')).split(',').filter(Boolean)]
let ethers
for (const d of DEPS) { try { ethers = createRequire(path.join(d, 'package.json'))('ethers').ethers; break } catch { /* next */ } }
if (!ethers) { console.log('cannot run: npm install in this folder first (ethers)'); process.exit(3) }
const B64 = (b) => Buffer.from(b).toString('base64url')
const sha = (b) => createHash('sha256').update(b).digest()

class Key {
  constructor() {
    const { privateKey, publicKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' })
    this.priv = privateKey; const j = publicKey.export({ format: 'jwk' })
    this.jwk = { kty: 'EC', crv: 'P-256', x: j.x, y: j.y }
    this.jkt = B64(sha(JSON.stringify({ crv: 'P-256', kty: 'EC', x: j.x, y: j.y })))
  }
  proof(method, route, body = '', token = null) {
    const ts = Math.floor(Date.now() / 1000), rand = B64(randomBytes(16)), th = token ? B64(sha(token)) : '-'
    const text = ['vx-relay-proof-v1', method, RELAY + route, String(ts), rand, B64(sha(Buffer.from(body))), th].join('\n')
    const sig = edsign('sha256', Buffer.from(text), { key: this.priv, dsaEncoding: 'ieee-p1363' })
    return `v1.${this.jkt}.${ts}.${rand}.${B64(sig)}`
  }
}
async function req(method, route, body, { key, token, headers = {}, proof = true } = {}) {
  const data = body === undefined ? '' : JSON.stringify(body)
  const h = { 'content-type': 'application/json', accept: 'application/json', origin: APP, 'user-agent': 'Mozilla/5.0 relay-signin-check', ...headers }
  if (token) h.authorization = `Bearer ${token}`
  if (key && proof) h['vx-proof'] = key.proof(method, route, data, token)
  for (const [k, v] of Object.entries(h)) if (v === null) delete h[k]
  const r = await fetch(RELAY + route, { method, headers: h, body: method === 'POST' ? data : undefined, signal: AbortSignal.timeout(20000) })
  let j = null; try { j = await r.json() } catch { /* not json */ }
  return [r.status, j]
}
const held = (s, b) => s !== 200 && !(b && typeof b.device === 'object')
const nonce = (acct, key, purpose = 'signin', token) => req('POST', '/ai/nonce', { purpose, wallet: acct.address, jwk: key.jwk }, { key, token })
async function signin(acct, key, edit) {
  const [s, n] = await nonce(acct, key)
  if (s !== 200) throw new Error(`nonce answered ${s}: ${JSON.stringify(n).slice(0, 160)}`)
  const text = edit ? edit(n.message) : n.message
  const [s2, out] = await req('POST', '/ai/signin', { message: text, signature: await acct.signMessage(text), jwk: key.jwk, name: 'check' }, { key })
  return [s2, out, n.message]
}

const cases = []
const ok = (name, good, detail) => { cases.push({ case: name, held: !!good, detail }); console.log(`  ${good ? 'PASS' : 'FAIL'}  ${name}  ${JSON.stringify(detail).slice(0, 220)}`) }
try {
  const victim = ethers.Wallet.createRandom(), vkey = new Key()
  // the text the relay issues names the real app's host — a phishing origin cannot get one naming itself
  const [s0, n0] = await req('POST', '/ai/nonce', { purpose: 'signin', wallet: victim.address, jwk: vkey.jwk }, { key: vkey, headers: { origin: 'https://testnet-vordex.example' } })
  ok('a nonce asked from a look-alike origin is refused, or names the real host', s0 !== 200 || String(n0?.message ?? '').startsWith(`${HOST} wants you`), { status: s0, first: String(n0?.message ?? '').split('\n')[0] })
  const [s0b, n0b] = await req('POST', '/ai/nonce', { purpose: 'signin', wallet: victim.address, jwk: vkey.jwk }, { key: vkey, headers: { origin: null } })
  ok('a nonce asked with no origin (a script, not a browser) is refused, or names the real host', s0b !== 200 || String(n0b?.message ?? '').startsWith(`${HOST} wants you`), { status: s0b })
  let [s, b] = await signin(victim, vkey, (t) => t.replace(HOST, 'testnet-vordex.example'))
  ok('a sign-in text naming the clone\'s domain is refused', held(s, b), { status: s, error: b?.error })
  ;[s, b] = await signin(victim, vkey, (t) => t.split('\n').map((x) => (x.startsWith('Nonce: ') ? `Nonce: ${randomBytes(16).toString('hex')}` : x)).join('\n'))
  ok('a nonce the relay never issued is refused', held(s, b), { status: s, error: b?.error })
  ;[s, b] = await signin(victim, vkey, (t) => t.replace(/Chain ID: \d+/, 'Chain ID: 101101'))
  ok('a text for another chain is refused', held(s, b), { status: s, error: b?.error })
  // a good text + signature captured by the clone and redeemed with its own device key
  const [sn, n] = await nonce(victim, vkey); if (sn !== 200) throw new Error(`nonce ${sn}`)
  const text = n.message, good = await victim.signMessage(text), thief = new Key()
  const [t1, tb1] = await req('POST', '/ai/signin', { message: text, signature: good, jwk: thief.jwk }, { key: thief })
  const [t2, tb2] = await req('POST', '/ai/signin', { message: text, signature: good, jwk: vkey.jwk }, { key: thief })
  ok('a captured text + signature redeemed with another device key is refused', held(t1, tb1) && held(t2, tb2), { own: [t1, tb1?.error], victimJwk: [t2, tb2?.error] })
  // control: the victim's own sign-in works once; then the nonce is spent
  ;[s, b] = await req('POST', '/ai/signin', { message: text, signature: good, jwk: vkey.jwk, name: 'victim' }, { key: vkey })
  if (s !== 200) throw new Error(`the control sign-in was refused (${s} ${JSON.stringify(b).slice(0, 120)})`)
  const vtok = b.device.token
  ;[s, b] = await req('POST', '/ai/signin', { message: text, signature: good, jwk: vkey.jwk }, { key: vkey })
  ok('a nonce used once is refused the second time', held(s, b), { status: s, error: b?.error })
  // a stolen token without the device key
  const [a1] = await req('GET', '/ai/state', undefined, { token: vtok, proof: false })
  const [a2] = await req('GET', '/ai/state', undefined, { key: new Key(), token: vtok })
  ok('a stolen device token without the device key is refused (no proof / another key)', a1 === 401 && a2 === 401, { noProof: a1, otherKey: a2 })
  // a captured request proof replayed, and moved to another route
  const p = vkey.proof('GET', '/ai/state', '', vtok)
  const [r1] = await req('GET', '/ai/state', undefined, { token: vtok, headers: { 'vx-proof': p }, proof: false })
  const [r2] = await req('GET', '/ai/state', undefined, { token: vtok, headers: { 'vx-proof': p }, proof: false })
  const [r3] = await req('POST', '/ai/stop-all', {}, { token: vtok, headers: { 'vx-proof': vkey.proof('POST', '/ai/push/remove', '{}', vtok) }, proof: false })
  ok('a captured request proof works once, is refused on replay and on another route', r1 === 200 && r2 === 401 && r3 === 401, { first: r1, replay: r2, moved: r3 })
  // the residual: a clone with its own key gets the victim to sign the CORRECT text (the wallet shows the real host)
  const ckey = new Key(); const [cs, cb] = await signin(victim, ckey)
  const residual = { cloneGotSignIn: cs === 200 }
  if (cs === 200) {
    const ctok = cb.device.token
    residual.noOrderRoute = (await req('POST', '/ai/order', {}, { key: ckey, token: ctok }))[0] === 404
    const [ns, nn] = await nonce(victim, vkey, 'signout', vtok)
    const [so] = await req('POST', '/ai/devices/signout', { scope: 'others', message: nn?.message, signature: ns === 200 ? await victim.signMessage(nn.message) : '' }, { key: vkey, token: vtok })
    residual.victimSignsOutOthers = so
    residual.cloneAfter = (await req('GET', '/ai/state', undefined, { key: ckey, token: ctok }))[0]
    residual.victimAfter = (await req('GET', '/ai/state', undefined, { key: vkey, token: vtok }))[0]
    residual.contained = residual.cloneAfter === 401 && residual.victimAfter === 200 && residual.noOrderRoute
  }
  console.log(`  NOTE  residual (stopped only by the wallet showing the real host): ${JSON.stringify(residual)}`)
  if (OUT) { mkdirSync(OUT, { recursive: true }); writeFileSync(path.join(OUT, 'r01-relay-signin.json'), JSON.stringify({ relay: RELAY, app: APP, at: new Date().toISOString(), cases, residual }, null, 1)) }
} catch (e) { console.log(`cannot run: ${e.message}`); process.exit(3) }
const works = cases.filter((c) => !c.held)
console.log(`r01-relay-signin: ${cases.length - works.length} pass, ${works.length} fail`)
process.exit(works.length ? 1 : 0)
