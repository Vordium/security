/**
 * Loads app source modules (TypeScript) for the source-level checks: each file is transpiled with the app's OWN
 * typescript and evaluated in a tiny CommonJS loader. `@/x` resolves to <app>/src/x; packages resolve from the app's
 * node_modules. Nothing is written anywhere.
 *   const app = makeLoader(APP_DIR, { env: { NEXT_PUBLIC_VORDIUM_NETWORK: 'mainnet' } }); app('src/lib/builder.ts')
 */
import { readFileSync, existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'

export function makeLoader(appDir, opts = {}) {
  const req = createRequire(path.join(appDir, 'package.json'))
  const ts = req('typescript')
  if (!globalThis.__vxLoaderSaid) { globalThis.__vxLoaderSaid = 1; let ev = '?'; try { ev = JSON.parse(readFileSync(path.join(appDir, 'node_modules/ethers/package.json'), 'utf8')).version } catch { /* none */ } console.log(`  app source: typescript ${ts.version}, ethers ${ev} (from the app's own packages)`) }
  for (const [k, v] of Object.entries(opts.env ?? {})) process.env[k] = v
  const cache = new Map()
  const stubs = opts.stubs ?? {}
  const resolveFile = (p) => {
    for (const c of [p, `${p}.ts`, `${p}.tsx`, `${p}.js`, `${p}.json`, path.join(p, 'index.ts'), path.join(p, 'index.tsx')]) if (existsSync(c) && !c.endsWith('/')) { try { readFileSync(c); return c } catch { /* a folder */ } }
    return null
  }
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports
    const m = { exports: {} }
    cache.set(file, m)
    if (file.endsWith('.json')) { m.exports = JSON.parse(readFileSync(file, 'utf8')); m.exports.default = m.exports; return m.exports }
    const out = ts.transpileModule(readFileSync(file, 'utf8'), { fileName: file, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: opts.jsx === 'react-jsx' ? ts.JsxEmit.ReactJSX : ts.JsxEmit.React, esModuleInterop: true, resolveJsonModule: true } }).outputText
    const localRequire = (spec) => {
      if (spec in stubs) return stubs[spec]
      let target = null
      if (spec.startsWith('@/')) target = resolveFile(path.join(appDir, 'src', spec.slice(2)))
      else if (spec.startsWith('.')) target = resolveFile(path.resolve(path.dirname(file), spec))
      if (target) return load(target)
      return req(spec)
    }
    new Function('module', 'exports', 'require', '__filename', '__dirname', out)(m, m.exports, localRequire, file, path.dirname(file))
    return m.exports
  }
  return (rel) => load(resolveFile(path.join(appDir, rel)) ?? (() => { throw new Error(`no such source file: ${rel}`) })())
}

export const argOf = (k, d) => { const a = process.argv; const i = a.indexOf(k); return i > 0 ? a[i + 1] : d }
export function reporter(name) {
  let pass = 0, fail = 0; const lines = []
  const ck = (c, m, x = '') => { c ? pass++ : fail++; const l = `  ${c ? 'PASS' : 'FAIL'}  ${m}${!c && x !== '' ? ' — ' + String(x).slice(0, 400) : ''}`; console.log(l); lines.push(l); return !!c }
  const done = () => { console.log(`${name}: ${pass} pass, ${fail} fail`); process.exit(fail ? 1 : 0) }
  return { ck, done, lines, get pass() { return pass }, get fail() { return fail } }
}
