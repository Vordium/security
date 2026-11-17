// Make the kit file testnet-signing-vectors.json from the JS SDK (one time; c09 and c10 then check against it).
// Run: node make-testnet-vectors.mjs
process.argv.push('--write')
await import('./c10_vectors_js.mjs')
