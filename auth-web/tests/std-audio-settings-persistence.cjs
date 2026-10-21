const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')
const route = fs.readFileSync(path.join(__dirname, '../app/api/std/projects/[projectId]/route.ts'), 'utf8')
const start = route.indexOf("    if (projectPayloadPatch.render_settings && ['audio', 'subtitle']")
const end = route.indexOf('    if (projectPayloadPatch.render_settings?.comic', start)
assert.ok(start >= 0 && end > start)
const code = ts.transpileModule(route.slice(start, end), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
const merge = new Function('body', 'projectPayloadPatch', 'project', code + '\nreturn projectPayloadPatch.render_settings')
test('stale subtitle style save cannot restore a deleted SFX or overwrite uploaded BGM', () => {
    const cues = [{ id: 'knock', enabled: false, user_override: true }]
    const result = merge({ render_settings_scope: 'subtitle' }, { render_settings: {
        subtitle_font_size: 6, sfx_cues: [{ id: 'knock', enabled: true }], bgm_asset_id: 'old',
    } }, { project_payload: { render_settings: { sfx_cues: cues, bgm_asset_id: 'new', bgm_volume: .08 } } })
    assert.deepEqual(result.sfx_cues, cues)
    assert.equal(result.bgm_asset_id, 'new')
    assert.equal(result.subtitle_font_size, 6)
})
test('audio save preserves latest subtitle style and stores the deletion tombstone', () => {
    const cues = [{ id: 'knock', enabled: false, user_override: true }]
    const result = merge({ render_settings_scope: 'audio' }, { render_settings: { subtitle_font_size: 3, sfx_cues: cues } },
        { project_payload: { render_settings: { subtitle_font_size: 6, bgm_asset_id: 'old', bgm_file_name: 'old.mp3' } } })
    assert.equal(result.subtitle_font_size, 6)
    assert.deepEqual(result.sfx_cues, cues)
    assert.equal(result.bgm_asset_id, undefined)
})

test('submitted subtitle and audio saves preserve frozen motion without validating or normalizing it', () => {
    // Legacy key order and fields may differ from a normalized current draft.
    const motion = { scenes: {}, enabled: false, version: 1, fps: 24, aspect: '16:9', legacy: true }
    const comic = { version: 1, mode: 'moving_comic' }
    for (const scope of ['subtitle', 'audio']) {
        const current = { motion, comic, subtitle_font_size: 5.4 }
        const result = merge({ render_settings_scope: scope }, { render_settings: {
            motion: { ...motion, enabled: true, final_renderer: 'filmcraft' },
            comic: { version: 1, mode: 'other' }, subtitle_font_size: 6,
            sfx_cues: [{ id: 'steps', enabled: true }],
        } }, { submitted_at: '2026-10-21T13:17:00Z', project_payload: { render_settings: current } })
        assert.strictEqual(result.motion, motion)
        assert.strictEqual(result.comic, comic)
        assert.equal(result.subtitle_font_size, scope === 'subtitle' ? 6 : 5.4)
    }
})

test('an explicit motion edit still rejects changes to a submitted timeline', () => {
    const normalizeMotionDraft = value => value
    const NextResponse = { json: (body, options) => ({ body, ...options }) }
    const run = new Function('body', 'projectPayloadPatch', 'project', 'normalizeMotionDraft', 'NextResponse', 'sceneManifest', code + '\nreturn projectPayloadPatch.render_settings')
    const motion = { scenes: {}, enabled: false }
    const result = run({}, { render_settings: { motion: { ...motion, enabled: true } } },
        { submitted_at: '2026-10-21T13:17:00Z', project_payload: { render_settings: { motion } } }, normalizeMotionDraft, NextResponse, [])
    assert.equal(result.status, 409)
    assert.match(result.body.error, /제출된 Motion/)
})
