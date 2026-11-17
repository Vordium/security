#!/usr/bin/env node
/**
 * (live, read-only GETs) — a look-alike or hostile page cannot put the real app in a frame and steer the
 * trader's clicks on it (clickjacking a signing button), and the app is only served over HTTPS with HSTS.
 *   - every app page answers frame-ancestors 'none' + X-Frame-Options DENY, and the page itself carries a script that
 *     blanks the page when it finds itself framed;
 *   - the one page made to be framed (the trade widget, test network only) signs nothing inside the frame; the main
 *     network answers it 404;
 *   - HSTS on every page; the Content-Security-Policy has no wildcard script source.
 *   node l01-frame-and-headers.mjs [--test https://testnet.vordex.xyz] [--main https://app.vordex.xyz]
 * exit 0 = defences hold · 1 = a page can be framed or lacks a header · 3 = cannot run
 */
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d }
const TEST = arg('--test', 'https://testnet.vordex.xyz'), MAIN = arg('--main', 'https://app.vordex.xyz')
const PAGES = ['/', '/futures', '/portfolio', '/settings', '/agents', '/mcp', '/bridge', '/rewards', '/referrals', '/staking', '/changelog']
let pass = 0, fail = 0
const ck = (c, m, x = '') => { c ? pass++ : fail++; console.log(`  ${c ? 'PASS' : 'FAIL'}  ${m}${!c && x !== '' ? ' — ' + String(x).slice(0, 300) : ''}`) }
const get = async (u) => { const r = await fetch(u, { redirect: 'manual', signal: AbortSignal.timeout(20000), headers: { 'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) app-signing-check' } }); return { status: r.status, h: r.headers, body: r.status === 200 ? await r.text() : '' } }
try { await get(`${TEST}/`) } catch (e) { console.log(`cannot run: ${e.message}`); process.exit(3) }
for (const [net, base] of [['test', TEST], ['main', MAIN]]) {
  for (const p of PAGES) {
    let r; try { r = await get(base + p) } catch (e) { ck(false, `${net} ${p}: reachable`, e.message); continue }
    if (r.status >= 300 && r.status < 400) { ck(true, `${net} ${p}: redirects (${r.status}) — judged at its target`); continue }
    if (r.status === 404) { ck(true, `${net} ${p}: not on this network (404)`); continue }
    const csp = r.h.get('content-security-policy') ?? '', fa = (/frame-ancestors ([^;]*)/.exec(csp) ?? [, ''])[1].trim()
    ck(fa === "'none'" && /^deny$/i.test(r.h.get('x-frame-options') ?? ''), `${net} ${p}: frame-ancestors 'none' and X-Frame-Options DENY`, `${fa} / ${r.h.get('x-frame-options')}`)
    ck(/max-age=\d{7,}/.test(r.h.get('strict-transport-security') ?? ''), `${net} ${p}: HSTS`, r.h.get('strict-transport-security'))
    const ss = (/script-src ([^;]*)/.exec(csp) ?? [, ''])[1]
    ck(!!ss && !/(^|\s)(\*|https:|'unsafe-eval')(\s|$)/.test(ss), `${net} ${p}: no wildcard or eval script source`, ss)
    ck(/window\.top\s*!==\s*window\.self/.test(r.body), `${net} ${p}: the page carries its own frame guard`)
  }
}
// the widget page
const wt = await get(`${TEST}/embed/trade`).catch(() => null), wm = await get(`${MAIN}/embed/trade`).catch(() => null)
if (wt && wt.status === 200) {
  const fa = (/frame-ancestors ([^;]*)/.exec(wt.h.get('content-security-policy') ?? '') ?? [, ''])[1].trim()
  ck(/^https:$/.test(fa), 'test /embed/trade: may be framed by https sites only (the widget)', fa)
  ck(!/signTypedData|eth_signTypedData_v4/.test(wt.body), 'test /embed/trade: the widget page itself asks for no signature')
} else ck(true, `test /embed/trade: not served (${wt?.status})`)
ck(wm?.status === 404, 'main /embed/trade: not served on the main network (404)', wm?.status)
console.log(`l01-frame-and-headers: ${pass} pass, ${fail} fail`)
process.exit(fail ? 1 : 0)
