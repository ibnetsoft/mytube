const assert = require('node:assert/strict'), fs = require('node:fs'), ts = require('typescript')
const out = {}
new Function('exports', ts.transpile(fs.readFileSync('auth-web/lib/stdHiddenVoiceIds.ts', 'utf8'), { module: 1, target: 7 }))(out)
assert.deepEqual(out.parseHiddenVoiceIds('["voice-1","voice-1"," voice-2 ",null]'), ['voice-1', 'voice-2'])
assert.deepEqual(out.parseHiddenVoiceIds('invalid'), [])
assert.deepEqual(out.parseHiddenVoiceIds(null), [])
assert.deepEqual(out.filterHiddenVoices([{ id: 'voice-1' }, { id: 'theo' }], ['voice-1']), [{ id: 'theo' }])
console.log('PASS: hidden voice settings are normalized')
