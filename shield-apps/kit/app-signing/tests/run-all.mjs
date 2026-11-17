#!/usr/bin/env node
// Runs every check in this folder and writes one log per check plus summary.txt into OUT.
//   node run-all.mjs OUT [APP_SOURCE_DIR]
// Checks are found by their file names: l… and r… (live, read-only or test network), t… (live, test network), u… (source
// checks, run when an app source folder is given), b… (browser checks, run when CHROME_PATH names a Chromium build;
// BASE=URL tests another build). DEPS=DIR[,DIR] names folders holding ethers / playwright-core.
import { spawnSync } from 'node:child_process'
import { appendFileSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
const HERE = path.dirname(fileURLToPath(import.meta.url))
const [OUT, APP] = process.argv.slice(2)
if (!OUT) { console.log('usage: node run-all.mjs OUT [APP_SOURCE_DIR]'); process.exit(3) }
mkdirSync(OUT, { recursive: true }); writeFileSync(path.join(OUT, 'summary.txt'), '')
const deps = process.env.DEPS ? ['--deps', process.env.DEPS] : []
const checks = readdirSync(HERE).filter((f) => /^[a-z]\d\d-[a-z0-9-]+\.mjs$/.test(f)).map((f) => f.slice(0, -4)).sort()
let worst = 0
const run = (name, args) => {
  const r = spawnSync(process.execPath, [path.join(HERE, `${name}.mjs`), ...args], { encoding: 'utf8', timeout: 600_000 })
  const out = (r.stdout ?? '') + (r.stderr ?? ''); writeFileSync(path.join(OUT, `${name}.log`), out)
  const rc = r.status ?? 3; worst = Math.max(worst, rc === 3 ? 3 : rc)
  const line = `${name} rc=${rc} ${(out.match(/^[a-z0-9-]+: \d+ pass, \d+ fail$/gm) ?? ['']).pop()}`
  console.log(line); appendFileSync(path.join(OUT, 'summary.txt'), line + '\n')
}
for (const c of checks) {
  const k = c[0]
  if (k === 'l') run(c, [])
  else if (k === 'r' || k === 't') run(c, ['--out', OUT, ...deps])
  else if (k === 'u' && APP) run(c, ['--app', APP])
  else if (k === 'b' && process.env.CHROME_PATH) run(c, ['--out', path.join(OUT, c.slice(0, 3)), '--chrome', process.env.CHROME_PATH, ...(process.env.BASE ? ['--base', process.env.BASE] : []), ...deps])
}
process.exit(worst)
