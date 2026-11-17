#!/usr/bin/env node
/**
 * Source check (run): a vaults read that names another deposit vault, with the published code hashes, is not used, and
 * an approval made for a deposit is for exactly the amount deposited.
 *   - the app's own deployment check is run on a read naming a different vault (and its handler): it must refuse it;
 *   - the same read naming the published vault passes the check (the control);
 *   - the deposit the app builds for the published vault approves exactly the amount (never an unlimited allowance).
 *   node u07-deposit-pins.mjs --app <app source dir>
 * exit 0 = the app refuses the other vault and approves the exact amount · 1 = otherwise · 3 = cannot run
 */
import { existsSync } from 'node:fs'
import path from 'node:path'
import { makeLoader, argOf, reporter } from './lib/load-app.mjs'

const APP = argOf('--app')
if (!APP || !existsSync(path.join(APP, 'src/lib/bridgeV4.ts'))) { console.log('cannot run: --app <app source dir> is required'); process.exit(3) }
const R = reporter('u07-deposit-pins')
const B = makeLoader(APP, { env: { NEXT_PUBLIC_VORDIUM_NETWORK: 'mainnet', NEXT_PUBLIC_BRIDGE_V4: 'on' } })('src/lib/bridgeV4.ts')
const dep = B.DEPLOYMENTS['42161']
if (!dep) { console.log('cannot run: no published deployment in this build'); process.exit(3) }
const OTHER = '0x' + 'ab'.repeat(20), OTHER_H = '0x' + 'cd'.repeat(20)
const read = (vault, handler) => ({
  active: true, as_of: { height: 7 },
  vaults: [{ id: 1, chain_id: 42161, address: vault, handler, cctp_domain: 3, deposits: { direct: { chain_id: 42161, minimum_6dec: '1000000' } },
    withdrawals: { routes: [{ route_kind: 0, name: 'local', open: true }], fee_6dec: '1000000' },
    runtime_sha256: { vault: B.PINS.vault.runtime, handler: B.PINS.handler.runtime }, binding: { handler_vault: vault, local_domain: 3, usdc: '0x' + 'ee'.repeat(20), confirmed: true } }],
  depositsOpen: { 42161: true }, minimumDeposit6dec: { 42161: '1000000' }, withdrawalFee6dec: '1000000',
})
const bad = B.deploymentCheck(B.readVaults(read(OTHER, OTHER_H)))
R.ck(bad.ok === false, 'a read naming another vault (with the published code hashes) is refused', JSON.stringify(bad, (k, v) => (typeof v === "bigint" ? String(v) : v)).slice(0, 160))
const badH = B.deploymentCheck(B.readVaults(read(dep.vault, OTHER_H)))
R.ck(badH.ok === false, 'a read naming the published vault with another handler is refused', JSON.stringify(badH, (k, v) => (typeof v === "bigint" ? String(v) : v)).slice(0, 160))
const good = B.deploymentCheck(B.readVaults(read(dep.vault, dep.handler)))
R.ck(good.ok === true, 'the published vault and handler pass (control)', JSON.stringify(good, (k, v) => (typeof v === "bigint" ? String(v) : v)).slice(0, 160))
try {
  const amt = 25_000_000n, usdc = '0x' + 'ee'.repeat(20)
  const chk = B.depositCheck(good, 42161, amt)
  const txs = B.directDepositTxs(chk, good, 42161, usdc, amt, { ok: true, outcome: 'accepted' })
  const ap = txs.find((t) => t.label === 'Approve USDC'), d = ap?.data ?? ''
  R.ck(ap && ap.to === usdc && d.slice(0, 10) === '0x095ea7b3' && d.slice(10, 74).toLowerCase().endsWith(dep.vault.slice(2).toLowerCase()) && BigInt('0x' + d.slice(74, 138)) === amt,
    'the deposit approval names the published vault and exactly the amount deposited', d)
  R.ck(txs.find((t) => t.label === 'Deposit')?.to?.toLowerCase() === dep.vault.toLowerCase(), 'the deposit goes to the published vault')
} catch (e) { R.ck(false, 'the deposit transactions could be built', e.message) }
R.done()
