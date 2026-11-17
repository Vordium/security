// Shared helpers for the SDK re-run kit (JavaScript side): npm install (package.json names @vordium/sdk and ethers).
// Every test exits 0 = the defence holds, 1 = the attack works (or the requirement fails), 3 = cannot run.
export const MAINNET_GENESIS = '2c1c0679fa6ab8358f1d3e8d294a8d1c73ac2e2caf9079f1216abedc3d9fdf4f'
export const TESTNET_GENESIS = '8b5d414c5cd5d18bc468b64f87ac8e2c2b5ff494c769d5e09dcf50ce75a59792'

export class Results {
  constructor(title) {
    this.rows = []; this.cannot = []
    console.log('='.repeat(78)); console.log(title); console.log('='.repeat(78))
  }
  check(name, ok, detail = '') {
    this.rows.push([name, !!ok])
    console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ' -- ' + detail : ''}`)
    return ok
  }
  skip(name, why) { this.cannot.push(name); console.log(`[CANNOT RUN] ${name} -- ${why}`) }
  finish() {
    const fails = this.rows.filter(([, ok]) => !ok).map(([n]) => n)
    console.log('-'.repeat(78))
    console.log(`checks: ${this.rows.length - fails.length} pass, ${fails.length} fail, ${this.cannot.length} cannot run`)
    if (fails.length) { console.log('RESULT: ATTACK WORKS / REQUIREMENT FAILS (exit 1): ' + fails.join('; ')); process.exit(1) }
    if (!this.rows.length) { console.log('RESULT: CANNOT RUN (exit 3)'); process.exit(3) }
    console.log('RESULT: DEFENDED (exit 0)'); process.exit(0)
  }
}

/**
 * A fake network for the SDK's injectable transport: no sockets. `ident` = {chainId, genesis, rpcChainId?, testnet?}.
 * Records every POST body (exact bytes). `post` handlers may be set per path.
 */
export function fakeNet(ident, base = 'http://fake.invalid') {
  const log = []
  const handlers = {}
  const t = {
    ident,
    log,
    handlers,
    async get(url) {
      const p = new URL(url).pathname
      log.push({ method: 'GET', path: p })
      if (p.endsWith('/network-spec.json')) return { status: 200, body: { chainId: t.ident.chainId, genesisSha256: t.ident.genesis, testnet: t.ident.testnet ?? true } }
      if (p.endsWith('/status')) return { status: 200, body: { chain_id: t.ident.chainId, genesis_sha256: t.ident.genesis } }
      if (handlers['GET ' + p]) return handlers['GET ' + p]()
      return { status: 404, body: { error: 'not found' } }
    },
    async post(url, body) {
      const p = new URL(url).pathname
      log.push({ method: 'POST', path: p, body })
      if (p === '/rpc') {
        const m = JSON.parse(body).method
        if (m === 'eth_chainId') {
          const c = t.ident.rpcChainId ?? t.ident.chainId
          return { status: 200, body: { result: typeof c === 'string' ? c : '0x' + BigInt(c).toString(16) }, retryAfter: null }
        }
        return { status: 200, body: { error: { code: -32601 } }, retryAfter: null }
      }
      if (handlers['POST ' + p]) return handlers['POST ' + p](body)
      return { status: 404, body: { error: 'not found' }, retryAfter: null }
    },
  }
  t.preset = (name) => ({ name, spec: base + '/network-spec.json', rpc: base + '/rpc', api: base })
  return t
}

/** The version of @vordium/sdk this run actually imported (read from the package it resolved to). */
export async function sdkVersion() {
  try {
    const { readFileSync, existsSync } = await import('node:fs')
    const { dirname, join } = await import('node:path')
    const { fileURLToPath } = await import('node:url')
    let d = dirname(fileURLToPath(import.meta.resolve('@vordium/sdk')))
    for (let i = 0; i < 6; i++) {
      const p = join(d, 'package.json')
      if (existsSync(p)) { const j = JSON.parse(readFileSync(p, 'utf8')); if (j.name === '@vordium/sdk') return j.version }
      d = dirname(d)
    }
  } catch { /* unknown */ }
  return 'unknown'
}
export const SDK_VERSION = await sdkVersion()
