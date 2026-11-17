// Run the SDK checks and keep each one's output and exit code.
//   node run-all.mjs OUT_DIR [--offline] [PREFIX ...]
// Python checks run with $PY (default python3, which needs `pip install vordium`); JS checks with this node
// (after `npm install` here). --offline skips the live test-network checks (file names with _live). PREFIX (e.g. c01 c13) runs
// only the checks whose file name starts with it. Each check exits 0 = defended, 1 = attack works / requirement fails,
// 3 = cannot run.
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const out = args.find((a) => !a.startsWith('--') && !/^c\d\d/.test(a))
if (!out) { console.log('usage: node run-all.mjs OUT_DIR [--offline] [PREFIX ...]'); process.exit(2) }
const offline = args.includes('--offline')
const only = args.filter((a) => /^c\d\d/.test(a))
const outDir = resolve(out)
mkdirSync(outDir, { recursive: true })
const state = mkdtempSync(join(tmpdir(), 'vordium-kit-'))
const env = { ...process.env, VORDIUM_STATE_DIR: join(state, 'nonces'), PYTHONDONTWRITEBYTECODE: '1', HOME: state }
const py = process.env.PY || 'python3'
const tests = readdirSync(here).filter((f) => /^c\d\d_.*\.(py|mjs)$/.test(f)).sort()
const rows = ['test\texit\tresult']
for (const t of tests) {
  if (only.length && !only.some((p) => t.startsWith(p))) continue
  if (offline && /_live/.test(t)) { rows.push(`${t}\t-\tskipped (offline)`); continue }
  const cmd = t.endsWith('.py') ? py : process.execPath
  const r = spawnSync(cmd, [t], { cwd: here, env, encoding: 'utf8', timeout: 290_000, maxBuffer: 64 * 1024 * 1024 })
  writeFileSync(join(outDir, t.replace(/\.(py|mjs)$/, '') + '.log'), (r.stdout || '') + (r.stderr || ''))
  const rc = r.status ?? 'timeout'
  const res = rc === 0 ? 'DEFENDED' : rc === 1 ? 'ATTACK WORKS / REQUIREMENT FAILS' : rc === 3 ? 'CANNOT RUN' : `ERROR (${rc})`
  rows.push(`${t}\t${rc}\t${res}`)
  console.log(`${t.padEnd(28)} exit ${rc}  ${res}`)
}
writeFileSync(join(outDir, 'summary.tsv'), rows.join('\n') + '\n')
rmSync(state, { recursive: true, force: true })
