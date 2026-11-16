const assert = require('node:assert/strict')
const test = require('node:test')
const load = require('./load-ts-module.cjs')
const { topicThumbnailPayloads, restoreTopicThumbnail } = load(require('node:path').resolve(__dirname, '../lib/stdTopicThumbnail.ts'))
const design = { contract: 'editable-background-v1', editor_bg_url: '/bg.png', bg_url: '/bg.png',
    thumbnail_url: '/final.png', render_status: 'completed', text_layers: [{ text: '우린 살아 있다' }] }
const topic = { id: 3432, progress_payload: { thumbnail_bg_url: '/bg.png', thumbnail_url: '/final.png',
    thumbnail_design: design, thumbnail_completed: true } }
const legacy = () => ({ topic_queue_id: 3432, project_payload: { thumbnail_bg_url: '/bg.png', script: 'keep' },
    progress_payload: { tts_completed: true } })
test('claim transfers final, editable background, lettering and verified completion together', () => {
    const p = topicThumbnailPayloads(topic)
    assert.equal(p.project_payload.thumbnail_url, '/final.png')
    assert.deepEqual(p.project_payload.thumbnail_design, design)
    assert.equal(p.progress_payload.thumbnail_completed, true)
    assert.equal(p.project_payload.thumbnail_bg_url, '/bg.png')
})
test('legacy reopen restores missing package without mutating saved work; repeat is idempotent', () => {
    const original = legacy(), restored = restoreTopicThumbnail(original, topic)
    assert.equal(restored.project_payload.thumbnail_url, '/final.png')
    assert.equal(restored.project_payload.script, 'keep')
    assert.equal(restored.progress_payload.tts_completed, true)
    assert.equal(original.project_payload.thumbnail_design, undefined)
    assert.strictEqual(restoreTopicThumbnail(restored, topic), restored)
    assert.deepEqual(restoreTopicThumbnail({ ...original, source_payload: topic }).project_payload.thumbnail_design, design)
})
test('user draft, final, changed background, strict content and unrelated topics are preserved', () => {
    for (const patch of [{ thumbnail_design: { text_layers: [] } }, { thumbnail_url: '/user.png' },
        { thumbnail_bg_url: '/user-bg.png' }, { strict_content_identity: true }]) {
        const p = legacy(); Object.assign(p.project_payload, patch)
        assert.strictEqual(restoreTopicThumbnail(p, topic), p)
    }
    const p = legacy(); assert.strictEqual(restoreTopicThumbnail(p, { ...topic, id: 3428 }), p)
})
test('invalid final does not inherit a false completed status', () => {
    const p = topicThumbnailPayloads({ progress_payload: { ...topic.progress_payload,
        thumbnail_url: '/bg.png', thumbnail_design: { ...design, thumbnail_url: '/bg.png' } } })
    assert.notEqual(p.progress_payload.thumbnail_completed, true)
})
test('source structure design remains usable when old topic progress lacks design', () => {
    const p = topicThumbnailPayloads({ progress_payload: { thumbnail_completed: true }, pregenerated_structure: { thumbnail_design: design } })
    assert.equal(p.project_payload.thumbnail_url, '/final.png')
    assert.deepEqual(p.project_payload.thumbnail_design.text_layers, design.text_layers)
})
