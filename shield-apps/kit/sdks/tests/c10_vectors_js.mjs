// C-18..C-21 (JavaScript SDK): signing against the published test vectors and the chain's own type strings.
// C-18 the official agent-op vectors (github.com/Vordium/node, vectors/agent-ops-vectors-2c1c0679.json): the SDK
//      rebuilds the domain separator and every digest, and its signatures with the public test keys equal the vectors'.
// C-19 every type string the network spec publishes (both networks) equals the SDK's.
// C-20 test-network vectors for EVERY operation the SDK signs: the SDK's output is compared byte for byte with the kit's
//      file testnet-signing-vectors.json (made once by make-testnet-vectors.mjs; the Python SDK is checked against the
//      same file in c09, independently).
// C-35 no two operations share a field list.
// Run: node c10_vectors_js.mjs   (reads two public URLs; --vectors FILE to use a local copy of the official vectors)
// Exit: 0 all equal, 1 a mismatch, 3 cannot run.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { TESTNET_GENESIS, Results, SDK_VERSION } from './_kit.mjs'

let sdk, ethers
try { sdk = await import('@vordium/sdk'); ethers = await import('ethers') } catch (e) { console.log('cannot import: ' + e.message); process.exit(3) }
const here = dirname(fileURLToPath(import.meta.url))
const OUT = join(here, 'testnet-signing-vectors.json')
const OFFICIAL = 'https://raw.githubusercontent.com/Vordium/node/main/vectors/agent-ops-vectors-2c1c0679.json'
const SPECS = { testnet: 'https://testnet.vordex.xyz/network-spec.json', mainnet: 'https://rpc.vordium.com/network-spec.json' }
const R = new Results('C-18..C-21 signing vectors, JS SDK @vordium/sdk ' + SDK_VERSION)
const argv = process.argv.slice(2)
const getJson = async (u) => { const r = await fetch(u, { headers: { accept: 'application/json' } }); if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() }

// ── C-18 official vectors ──────────────────────────────────────────────────────────────────────────────────────────
let off = null
try { off = argv.includes('--vectors') ? JSON.parse(readFileSync(argv[argv.indexOf('--vectors') + 1], 'utf8')) : await getJson(OFFICIAL) } catch (e) { R.skip('C-18 official vectors', `cannot read them: ${e.message}`) }
if (off) {
  const d = off.domain
  const dom = sdk.domain('VordCore', d.chainId, off.network.genesis_sha256)
  R.check('C-18a domain salt and separator', dom.salt === d.salt && sdk.separator('VordCore', d.chainId, off.network.genesis_sha256) === d.domainSeparator, d.domainSeparator)
  const known = new Set(Object.keys(sdk.TYPE_STRINGS))
  const ownerKey = off.test_keys.owner.private_key
  for (const v of off.canonical_vectors.vectors) {
    if (!known.has(v.op)) { console.log(`[note] ${v.op}: the SDK does not sign this op (the chain does not apply it)`); continue }
    R.check(`C-18b canonical ${v.op} digest`, sdk.digest(dom, v.op, v.message) === v.digest, v.digest)
  }
  for (const v of off.signed_vectors.vectors) {
    if (!known.has(v.op)) continue
    R.check(`C-18c signed ${v.op} digest`, sdk.digest(dom, v.op, v.message) === v.digest, v.digest)
    const ok = v.cases.find((c) => /^ACCEPTED/.test(c.expected) && /owner/.test(c.signedBy))
    if (ok) {
      const sig = await sdk.signOp(sdk.keySigner(ownerKey), dom, v.op, v.message)
      R.check(`C-18d ${v.op} signature with the public owner test key equals the vector`, sig === ok.signature.toLowerCase(), sig.slice(0, 20) + '…')
    }
  }
}

// ── C-19 type strings the network spec publishes ──────────────────────────────────────────────────────────────────
const published = []
for (const [net, url] of Object.entries(SPECS)) {
  let s
  try { s = await getJson(url) } catch (e) { R.skip(`C-19 ${net} spec`, e.message); continue }
  const walk = (x, p) => {
    if (x && typeof x === 'object') { for (const [k, v] of Object.entries(x)) walk(v, p + '/' + k); return }
    if (typeof x === 'string' && /^[A-Z][A-Za-z0-9]*\((?:[a-z0-9[\]]+ [A-Za-z0-9]+,?)*\)/.test(x) && /\b(uint|address|bytes32|bool)/.test(x)) published.push([net, p, x])
  }
  walk(s, '')
}
for (const [net] of Object.entries(SPECS)) if (!published.some(([n]) => n === net)) console.log(`[note] the ${net} spec publishes no type strings: nothing to compare there`)
let compared = 0
for (const [net, p, ts] of published) {
  const name = ts.slice(0, ts.indexOf('('))
  if (!(name in sdk.TYPE_STRINGS)) { console.log(`[note] ${net}${p}: ${name} is published but the JS SDK does not sign it`); continue }
  compared++
  R.check(`C-19 ${net} spec ${name} type string equals the SDK's`, ts.startsWith(sdk.TYPE_STRINGS[name]) && ts.length === sdk.TYPE_STRINGS[name].length, p)
}

R.check('C-19 the network specs published at least one type string to compare', compared > 0, `${compared} compared`)
{
  const by = new Map()
  for (const [op, ts] of Object.entries(sdk.TYPE_STRINGS)) { const f = ts.slice(ts.indexOf('(')); by.set(f, [...(by.get(f) ?? []), op]) }
  const dups = [...by.values()].filter((v) => v.length > 1)
  R.check(`C-35 no two of the SDK's ${Object.keys(sdk.TYPE_STRINGS).length} type strings share a field list`, dups.length === 0, JSON.stringify(dups))
}
// ── C-20 test-network vectors for every operation ──────────────────────────────────────────────────────────────────
const KEY_LABEL = 'vordium-rerun-kit:public-test-key:signer'
const key = '0x' + createHash('sha256').update(KEY_LABEL).digest('hex')
const signer = sdk.keySigner(key)
const addr = await signer.getAddress()
function sample(type, name, i) {
  if (type === 'address') return ethers.getAddress('0x' + createHash('sha256').update(name + i).digest('hex').slice(0, 40))
  if (type === 'bool') return i % 2 === 1
  if (type === 'string') return `vector ${name}`
  const m = /^uint(\d+)$/.exec(type)
  if (m) { const bits = Number(m[1]); const v = (BigInt(1_700_000_000_123) * BigInt(i + 3)) % (1n << BigInt(Math.min(bits, 60))); return (v === 0n ? 1n : v).toString() }
  throw new Error('no sample for ' + type)
}
function message(primary) {
  const types = sdk.typesFor(primary)
  const build = (t) => Object.fromEntries(types[t].map((f, i) => {
    if (f.type.endsWith('[]')) { const base = f.type.slice(0, -2); return [f.name, [build(base), build(base)]] }
    return [f.name, sample(f.type, f.name, i)]
  }))
  return build(primary)
}
const vectors = []
for (const op of Object.keys(sdk.TYPE_STRINGS)) {
  if (op === 'BatchAction') continue
  const cls = sdk.domainOf(op)
  const dom = sdk.domain(cls, 101102, TESTNET_GENESIS)
  const msg = message(op)
  const types = sdk.typesFor(op)
  vectors.push({ op, domainClass: cls, typeString: sdk.TYPE_STRINGS[op] + (types.BatchAction ? sdk.TYPE_STRINGS.BatchAction : ''),
    typeHash: ethers.keccak256(ethers.toUtf8Bytes(sdk.TYPE_STRINGS[op] + (types.BatchAction ? sdk.TYPE_STRINGS.BatchAction : ''))),
    message: msg, digest: sdk.digest(dom, op, msg), signature: await sdk.signOp(signer, dom, op, msg) })
}
const file = {
  about: 'Test-network signing vectors for every operation the SDKs sign. Built from the SDK type strings and checked against the network spec; the public test key is sha256 of the label (never funded).',
  network: { chainId: 101102, genesisSha256: TESTNET_GENESIS },
  domains: Object.fromEntries(['VordCore', 'VordexSession'].map((c) => [c, { name: c, version: '1', chainId: 101102, verifyingContract: sdk.VERIFYING_CONTRACT, salt: sdk.salt(c, TESTNET_GENESIS), separator: sdk.separator(c, 101102, TESTNET_GENESIS) }])),
  testKey: { label: KEY_LABEL, rule: 'private key = sha256(label)', address: addr },
  vectors,
}
const text = JSON.stringify(file, null, 1) + '\n'
if (argv.includes('--write')) { writeFileSync(OUT, text); console.log(`[wrote] ${OUT} (${vectors.length} operations)`); process.exit(0) }
if (!existsSync(OUT)) R.check('C-20 the kit file testnet-signing-vectors.json is present', false, OUT)
else {
  const stored = JSON.parse(readFileSync(OUT, 'utf8'))
  R.check('C-20 the kit file covers every operation the SDK signs', vectors.every((v) => stored.vectors.some((x) => x.op === v.op)), `${stored.vectors.length} stored, ${vectors.length} signed`)
  for (const v of vectors) {
    const s = stored.vectors.find((x) => x.op === v.op)
    R.check(`C-20 ${v.op}: digest and signature equal the stored vector`, !!s && s.digest === v.digest && s.signature === v.signature && s.typeString === v.typeString, v.digest)
  }
  for (const v of stored.vectors) {
    const rec = ethers.recoverAddress(v.digest, v.signature)
    if (rec !== addr) R.check(`C-20 ${v.op}: stored signature recovers to the test key`, false, rec)
  }
}
R.finish()
