// C-10..C-13 (JavaScript SDK): the persisted client-nonce allocator under concurrency, a crash and a clock set back.
// Run: node c06_nonces_js.mjs     Exit: 0 defended, 1 a nonce repeated or went back, 3 cannot run.
import { spawn } from 'node:child_process'
import { mkdtempSync, readdirSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ACCOUNT = '0x' + 'cd'.repeat(20)
const me = fileURLToPath(import.meta.url)
let sdk
try { sdk = await import('@vordium/sdk') } catch (e) { console.log('cannot import: ' + e.message); process.exit(3) }

if (process.argv[2] === '--child') {
  const [dir, n, tag] = [process.argv[3], Number(process.argv[4]), process.argv[5]]
  const store = sdk.fileNonceStore(dir)
  const workers = [0, 1, 2, 3].map(async (w) => {
    const a = new sdk.NonceAllocator(ACCOUNT, 'orders', store)
    for (let i = 0; i < n; i++) process.stdout.write(`${tag}${w} ${await a.next()}\n`)
  })
  await Promise.all(workers)
  process.exit(0)
}

const { Results, SDK_VERSION } = await import('./_kit.mjs')
const R = new Results('C-10..C-13 nonce allocator, JS SDK @vordium/sdk ' + SDK_VERSION)
const tmp = mkdtempSync(join(tmpdir(), 'vordium-nonce-'))
const dir = join(tmp, 'nonces')

function run(n, tag, killAfterMs = 0) {
  return new Promise((resolve) => {
    const p = spawn(process.execPath, [me, '--child', dir, String(n), tag], { stdio: ['ignore', 'pipe', 'inherit'] })
    let out = ''
    p.stdout.on('data', (d) => { out += d })
    let timer = null
    if (killAfterMs) timer = setTimeout(() => p.kill('SIGKILL'), killAfterMs)
    p.on('exit', () => { if (timer) clearTimeout(timer); resolve(out.split('\n').filter(Boolean).map((l) => l.split(' '))) })
  })
}

try {
  // C-10: 4 processes x 4 async workers x 60 nonces
  const rows = (await Promise.all([0, 1, 2, 3].map((i) => run(60, `p${i}w`)))).flat()
  const vals = rows.map(([, v]) => Number(v))
  const seqs = new Map()
  for (const [k, v] of rows) { if (!seqs.has(k)) seqs.set(k, []); seqs.get(k).push(Number(v)) }
  const rising = [...seqs.values()].every((s) => s.every((x, i) => i === 0 || x > s[i - 1]))
  R.check('C-10 16 workers x 60 nonces: all unique', vals.length === 960 && new Set(vals).size === vals.length, `${vals.length} taken, ${new Set(vals).size} distinct`)
  R.check("C-10b each worker's nonces strictly rise", rising, `${seqs.size} workers`)
  const top = Math.max(...vals)
  // C-11: crash
  const killed = (await run(1_000_000, 'k', 1500)).map(([, v]) => Number(v))
  const a = new sdk.NonceAllocator(ACCOUNT, 'orders', sdk.fileNonceStore(dir))
  const next = await a.next()
  const hi = Math.max(top, ...killed)
  R.check('C-11 after SIGKILL, the next nonce is above every one handed out', killed.length > 0 && next > hi, `killed after ${killed.length} nonces; next ${next} > ${hi}`)
  // C-12: clock back one hour
  let t = Date.now()
  const b = new sdk.NonceAllocator(ACCOUNT, 'orders', sdk.fileNonceStore(dir), () => t)
  const n1 = await b.next(); t -= 3_600_000
  const n2 = await b.next(); const n3 = await b.next()
  R.check('C-12 clock back one hour: nonces still rise', n1 < n2 && n2 < n3, `${n1} < ${n2} < ${n3}`)
  // C-13: modes
  const dmode = statSync(dir).mode & 0o777
  const fmodes = readdirSync(dir).map((f) => statSync(join(dir, f)).mode & 0o777)
  R.check('C-13 state folder 0700, mark files 0600', dmode === 0o700 && fmodes.every((m) => (m & 0o077) === 0), `folder ${dmode.toString(8)}; files ${[...new Set(fmodes.map((m) => m.toString(8)))].join(',')}`)
} catch (e) { R.check('C-10..13 ran', false, e.message) }
rmSync(tmp, { recursive: true, force: true })
R.finish()
