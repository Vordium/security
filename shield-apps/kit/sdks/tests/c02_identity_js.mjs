// C-01..C-07 (JavaScript SDK @vordium/sdk): chain id and genesis pinning against a hostile node.
// A fake network (the SDK's injectable transport, no sockets) claims one identity after another; for each, the SDK is
// asked to place an order. Defended when every hostile identity is refused before anything is signed or sent and the
// real test-network identity (the positive control) is signed for.
// Run: node c02_identity_js.mjs     Exit: 0 defended, 1 an identity was signed for, 3 cannot run.
import { randomBytes } from 'node:crypto'
import { MAINNET_GENESIS, TESTNET_GENESIS, Results, fakeNet, SDK_VERSION } from './_kit.mjs'

let sdk, ethers
try { sdk = await import('@vordium/sdk'); ethers = await import('ethers') } catch (e) { console.log('cannot import @vordium/sdk: ' + e.message); process.exit(3) }
const { Vordium, keySigner, NO_RULES } = sdk
const R = new Results('C-01..C-07 chain id + genesis pinning, JS SDK @vordium/sdk ' + SDK_VERSION)
const owner = keySigner(ethers.Wallet.createRandom().privateKey)
const session = keySigner(ethers.Wallet.createRandom().privateKey)

async function tryOrder(net, name) {
  net.handlers['POST /order/place'] = () => ({ status: 200, body: { status: 'submitted' }, retryAfter: null })
  const before = net.log.filter((r) => r.path === '/order/place').length
  let why = 'order sent'
  let pinProblem = null
  try {
    const c = await Vordium.connect({ network: net.preset(name), transport: net, chainClock: false, onPinProblem: (m) => { pinProblem = m } })
    const a = await c.account(owner, { sessionSigner: session, specs: NO_RULES })
    await a.placeOrder({ pairId: 1, side: 'buy', size: '0.01', price: '1000', orderType: 'Limit' })
  } catch (e) { why = `${e.name}: ${String(e.message).slice(0, 110)}` }
  const sent = net.log.filter((r) => r.path === '/order/place').length - before
  return { sent, why: (pinProblem ? 'pin problem reported; ' : '') + why }
}

async function kase(label, ident, name = 'testnet', expectSign = false) {
  const net = fakeNet(ident)
  const { sent, why } = await tryOrder(net, name)
  if (expectSign) R.check(`${label}: control is signed for`, sent === 1, why)
  else R.check(`${label}: nothing signed or sent`, sent === 0, why)
}

await kase("C-00 control (testnet identity, name 'testnet')", { chainId: 101102, genesis: TESTNET_GENESIS }, 'testnet', true)
await kase("C-01 node answers mainnet chain id for 'testnet'", { chainId: 101101, genesis: TESTNET_GENESIS })
await kase('C-01b eth_chainId disagrees with /status', { chainId: 101102, genesis: TESTNET_GENESIS, rpcChainId: 101101 })
await kase("C-02 foreign genesis for 'testnet'", { chainId: 101102, genesis: randomBytes(32).toString('hex') })
await kase('C-02b mainnet genesis with testnet chain id', { chainId: 101102, genesis: MAINNET_GENESIS })
await kase("C-02c foreign genesis with the main chain id for 'mainnet'", { chainId: 101101, genesis: randomBytes(32).toString('hex'), testnet: false }, 'mainnet')
await kase("C-02d test genesis with the main chain id for 'mainnet'", { chainId: 101101, genesis: TESTNET_GENESIS, testnet: false }, 'mainnet')
await kase("C-03 client names 'mainnet', node is the test network", { chainId: 101102, genesis: TESTNET_GENESIS, testnet: true }, 'mainnet')
await kase("C-03b client names 'testnet', node is the main network", { chainId: 101101, genesis: MAINNET_GENESIS, testnet: false })
await kase('C-04 unnamed preset claiming the mainnet identity (no pin)', { chainId: 101101, genesis: MAINNET_GENESIS, testnet: false }, 'my-node')
await kase('C-05 genesis with injected text', { chainId: 101102, genesis: '<script>alert(1)</script>' + '0'.repeat(39) })
await kase('C-05b chain id far past 64 bits', { chainId: 10n ** 40n, genesis: TESTNET_GENESIS, rpcChainId: '0x' + 'f'.repeat(40) })
await kase('C-05c negative chain id', { chainId: -101102, genesis: TESTNET_GENESIS })
await kase('C-05d chain id as text', { chainId: '101102; DROP', genesis: TESTNET_GENESIS })
await kase('C-05e genesis missing', { chainId: 101102, genesis: null })

// C-07: the node switches its genesis after the client connected; the next signature must be refused
{
  const net = fakeNet({ chainId: 101102, genesis: TESTNET_GENESIS })
  net.handlers['POST /order/place'] = () => ({ status: 200, body: { status: 'submitted' }, retryAfter: null })
  let first = false, why = 'signed after the switch'
  try {
    const c = await Vordium.connect({ network: net.preset('testnet'), transport: net, chainClock: false, identityTtlMs: 0 })
    const a = await c.account(owner, { sessionSigner: session, specs: NO_RULES })
    await a.placeOrder({ pairId: 1, side: 'buy', size: '0.01', price: '1000', orderType: 'Limit' })
    first = true
    net.ident.genesis = randomBytes(32).toString('hex')
    const before = net.log.filter((r) => r.path === '/order/place').length
    try { await a.placeOrder({ pairId: 1, side: 'buy', size: '0.01', price: '1000', orderType: 'Limit' }) } catch (e) { why = `${e.name}: ${String(e.message).slice(0, 100)}` }
    const sent = net.log.filter((r) => r.path === '/order/place').length - before
    R.check('C-07 node switches genesis after the first order: next order refused', first && sent === 0, why)
  } catch (e) { R.check('C-07 node switches genesis after the first order: next order refused', false, `setup failed: ${e.message}`) }
}
R.finish()
