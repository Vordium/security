#!/usr/bin/env node
/**
 * (source check) — the AI relay sign-in text (EIP-4361) is rebuilt by the page from its own facts before the
 * wallet sees it, so a lying or hijacked relay cannot get a sign-in for another site, account, chain or device signed;
 * and after a connect the browser is sent only to the place the user signed.
 * Runs the app's OWN checkMessage / redirectAllowed on the exact text and on hostile variants.
 *   node u04-siwe.mjs --app <app source dir>
 * exit 0 = every hostile text is refused and the exact one accepted · 1 = a hostile text passes · 3 = cannot run
 */
import { existsSync } from 'node:fs'
import path from 'node:path'
import { makeLoader, argOf, reporter } from './lib/load-app.mjs'

const APP = argOf('--app')
if (!APP || !existsSync(path.join(APP, 'src/lib/siwe.ts'))) { console.log('cannot run: --app <app source dir> is required'); process.exit(3) }
const R = reporter('u04-siwe')
const S = makeLoader(APP, {})('src/lib/siwe.ts')
const now = Math.floor(Date.now() / 1000), iso = (s) => new Date(s * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')
const W = { purpose: 'signin', host: 'testnet.vordex.xyz', origin: 'https://testnet.vordex.xyz', address: '0x52908400098527886E0F7030069857D2E4169EE7', chainId: 101102, jkt: 'abcdEFGH1234_-xyz', relay: 'https://mcp.vordium.com/testnet' }
const good = (w = W, o = {}) => [
  `${o.host ?? w.host} wants you to sign in with your Ethereum account:`, o.address ?? w.address, '', o.statement ?? S.STATEMENTS.signin, '',
  `URI: ${o.origin ?? w.origin}/mcp`, 'Version: 1', `Chain ID: ${o.chainId ?? w.chainId}`, `Nonce: ${o.nonce ?? '0123456789abcdef0123456789abcdef'}`,
  `Issued At: ${iso(o.iat ?? now)}`, `Expiration Time: ${iso(o.exp ?? now + 300)}`, 'Resources:', `- ${o.r1 ?? w.relay + '/ai'}`, `- ${o.r2 ?? 'urn:vordex:device:' + w.jkt}`,
  ...(o.extra ?? []),
].join('\n')
R.ck(S.checkMessage(good(), W) === null, 'the exact text this page expects is accepted')
const hostile = {
  'another site (look-alike host)': good(W, { host: 'testnet-vordex.xyz' }),
  'a host with a unicode look-alike letter': good(W, { host: 'testnet.vоrdex.xyz' }),
  'another account': good(W, { address: '0x000000000000000000000000000000000000dEaD' }),
  'another chain id (main network)': good(W, { chainId: 101101 }),
  'another URI origin': good(W, { origin: 'https://evil.example' }),
  'another device key': good(W, { r2: 'urn:vordex:device:ATTACKERKEY' }),
  'another relay resource': good(W, { r1: 'https://evil.example/ai' }),
  'a changed statement': good(W, { statement: 'Sign in to Vordex MCP. This device may move funds.' }),
  'a life longer than 5 minutes': good(W, { exp: now + 3600 }),
  'an expiry before issue': good(W, { exp: now - 10 }),
  'a short nonce': good(W, { nonce: '1234' }),
  'an extra trailing line': good(W, { extra: ['- https://evil.example/withdraw'] }),
  'a duplicated Nonce line': good(W, { extra: ['Nonce: ffffffffffffffffffffffffffffffff'] }),
  'a non-ASCII control text': good() + '‮',
  'an oversized text': good() + '\n' + 'x'.repeat(3000),
  'not a string': { text: good() },
}
for (const [k, t] of Object.entries(hostile)) R.ck(S.checkMessage(t, W) !== null, `refused: ${k}`)
// a connect: the redirect after signing goes only to the host the user signed
R.ck(S.redirectAllowed('https://app.example/cb?code=1', 'app.example'), 'redirect: the signed https host is allowed')
for (const [u, tok, why] of [
  ['javascript:alert(1)', 'app.example', 'javascript:'], ['data:text/html,x', 'app.example', 'data:'], ['https://app.example.evil.example/', 'app.example', 'a longer host'],
  ['http://app.example/', 'app.example', 'plain http to a remote host'], ['https://user:pw@app.example/', 'app.example', 'credentials in the URL'],
  ['http://evil.example/', 'local', 'a remote host for a local app'], ['https://app.example/', null, 'no signed host'], ['myapp://cb', 'scheme:other', 'another app scheme'],
]) R.ck(!S.redirectAllowed(u, tok), `redirect refused: ${why}`)
R.ck(S.asciiName('Ꭺрр‮Name<script>') === 'Name' || !/[^A-Za-z0-9 .,'&+-]/.test(S.asciiName('Ꭺрр‮Name<script>')), 'an AI app\'s self-given name is shown in plain ASCII only')
R.done()
