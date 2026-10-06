const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const exportsObject = {}
new Function('exports', ts.transpileModule(fs.readFileSync(require('node:path').resolve(__dirname, '../lib/stdSubtitlePersistence.ts'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exportsObject)
test('save waits beyond server duration and reports ambiguous timeout without retrying', async () => {
 assert.ok(exportsObject.SUBTITLE_SAVE_TIMEOUT_MS > 300000)
 let calls = 0
 const save = exportsObject.createSubtitleSaveQueue(async () => {calls++; throw new DOMException('signal timed out', 'TimeoutError')})
 await assert.rejects(save('p', {}, {}), /서버에 저장되었을 수/)
 assert.equal(calls, 1)
})
test('caller cancellation remains cancellation', async () => {
 const controller = new AbortController()
 controller.abort()
 const save = exportsObject.createSubtitleSaveQueue(async () => {throw new Error('must not send')})
 await assert.rejects(save('p', {}, {}, controller.signal), {name:'AbortError'})
})
