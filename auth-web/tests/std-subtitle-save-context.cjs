const test = require('node:test'), assert = require('node:assert/strict')
const { readSubtitleSaveContext, saveSubtitlePatchWithVerification } = require('./load-ts-module.cjs')('auth-web/lib/stdSubtitleSaveContext.ts')

test('temporary upstream errors retry the read but not permanent errors', async () => {
  let calls = 0; const waits = []
  const result = await readSubtitleSaveContext(async () => ++calls < 3
    ? { status: 520, error: { message: 'upstream unavailable' } }
    : { status: 200, error: null, data: { id: 'project' } }, async ms => waits.push(ms))
  assert.equal(result.data.id, 'project'); assert.equal(calls, 3); assert.deepEqual(waits, [500, 1500])
  calls = 0
  await readSubtitleSaveContext(async () => { calls++; return { status: 403, error: {} } }, async () => assert.fail('must not retry'))
  assert.equal(calls, 1)
})

test('persistent upstream failure stops after three read attempts', async () => {
  let calls = 0
  const result = await readSubtitleSaveContext(async () => { calls++; return { status: 521, error: {} } }, async () => {})
  assert.equal(result.status, 521); assert.equal(calls, 3)
})

test('ambiguous write is retried with the same version and verified without overwriting another edit', async () => {
  const payload = { subtitles: [{ text: 'keep', voice_id: 'chosen' }] }, progress = { subtitles_saved: true }
  let calls = 0
  const ok = await saveSubtitlePatchWithVerification(
    async () => ++calls === 1 ? { status: 520, error: {}, data: null } : { status: 200, error: null, data: null },
    async () => ({ status: 200, error: null, data: { project_payload: payload, progress_payload: progress } }),
    payload, progress, async () => {})
  assert.equal(calls, 2); assert.equal(ok.error, null); assert.equal(ok.data.project_payload.subtitles[0].voice_id, 'chosen')
  const changed = await saveSubtitlePatchWithVerification(
    async () => ({ status: 520, error: {}, data: null }),
    async () => ({ status: 200, error: null, data: { project_payload: { subtitles: [{ text: 'newer edit' }] }, progress_payload: progress } }),
    payload, progress, async () => {})
  assert.equal(changed.status, 503); assert.ok(changed.error); assert.equal(changed.data, null)
})
