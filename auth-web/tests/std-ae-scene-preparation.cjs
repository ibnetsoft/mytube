const test = require('node:test'), assert = require('node:assert/strict')
const load = require('./load-ts.cjs')
const { aeSceneHash, aeScenePreparationInput, preparedAeScenes, hasAeSceneIntent, aeSceneSources } = load(require('node:path').join(__dirname, '../lib/stdAeScenePreparation.ts'))
function fixture() {
    const project = { id: 'p', project_payload: { structure: { scenes: [] }, subtitles: [] } }
    const scenes = [{ scene_number: 1, scene_text: '그는 문을 연다.' }, { scene_number: 2, scene_text: '바람이 분다.' }]
    const assets = [{ id: 'psd', status: 'assigned', asset_type: 'original', scene_number: 1, file_name: 'scene.psd', created_at: '2026-10-01', metadata: { gcs_bucket: 'b', gcs_path: 'source.psd' } },
        { id: 'video', status: 'assigned', asset_type: 'video', scene_number: 1, file_name: 'clip.mp4', metadata: { gcs_bucket: 'b', gcs_path: 'clip.mp4' } }]
    const input = aeScenePreparationInput(project, scenes, assets, 1, '카메라 접근, 머리카락만 움직임')
    const plan = { contract: 'ae_scene/v1', camera: [{ t: 0, scale: 1 }, { t: 1, scale: 1.08 }] }
    const files = ['source_psd', 'source_preview', 'layer', 'plan', 'review'].map(role => ({ role, gcs_bucket: 'b', gcs_path: role, sha256: 'a'.repeat(64) }))
    assets.push({ id: 'prep', scene_number: 1, asset_type: 'other', status: 'uploaded', created_at: '2026-10-02',
        metadata: { kind: 'ae_scene_preparation', enabled: true, state: 'prepared', fingerprint: aeSceneHash(input), input,
            result: { source_asset_id: 'psd', source_sha256: 'a'.repeat(64), plan, plan_sha256: aeSceneHash(plan), files,
                review: { passed: true, critical_issues: [], input_fingerprint: aeSceneHash(input), source_sha256: 'a'.repeat(64),
                    plan_sha256: aeSceneHash(plan), reviewer: 'local_codex_cli', evidence: ['Actual original and layers inspected'],
                    source_identity_preserved: true, background_complete: true, motion_supported: true, continuity_checked: true } } } })
    return { project, scenes, assets }
}
test('manual clip and PSD can be prepared before final TTS, then reused when only timing changes', () => {
    const f = fixture()
    assert.equal(preparedAeScenes(f.project, f.scenes, f.assets).get(1).id, 'prep')
    f.project.project_payload.subtitles = [{ text: '그는 문을 연다.', start: 0, end: 8 }]
    f.project.project_payload.tts_speed = 1.2
    assert.equal(preparedAeScenes(f.project, f.scenes, f.assets).size, 1)
})
test('unrelated geometry annotations and unrelated original files do not invalidate the art', () => {
    const f = fixture()
    f.assets[1].metadata.speaker_geometry = { reviewed: true }
    f.assets.push({ ...f.assets[0], id: 'notes', file_name: 'notes.txt', created_at: '2026-11-01' })
    assert.equal(aeSceneSources(f.assets).get(1).id, 'psd')
    assert.equal(preparedAeScenes(f.project, f.scenes, f.assets).size, 1)
})
test('replacing PSD or clip requires a new direction review', () => {
    for (const index of [0, 1]) {
        const f = fixture()
        f.assets.push({ ...f.assets[index], id: 'new', created_at: '2026-11-01' })
        assert.throws(() => preparedAeScenes(f.project, f.scenes, f.assets), /바뀌었습니다/)
    }
})
test('neighbor narrative changes invalidate continuity while pure TTS changes do not', () => {
    const f = fixture()
    f.scenes[1].scene_text = '문을 다시 닫는다.'
    assert.throws(() => preparedAeScenes(f.project, f.scenes, f.assets), /바뀌었습니다/)
})
test('pending and failed requested direction never silently uses the uploaded clip', () => {
    for (const state of ['queued', 'processing', 'failed']) {
        const f = fixture()
        f.assets[2].metadata.state = state
        assert.equal(hasAeSceneIntent(f.project, f.scenes, f.assets), true)
        assert.throws(() => preparedAeScenes(f.project, f.scenes, f.assets), /AE 연출/)
    }
})
test('latest explicit disable supersedes older prepared jobs', () => {
    const f = fixture()
    f.assets.push({ ...f.assets[2], id: 'disabled', created_at: '2026-11-01', metadata: { ...f.assets[2].metadata, enabled: false, state: 'disabled' } })
    assert.equal(hasAeSceneIntent(f.project, f.scenes, f.assets), false)
    assert.equal(preparedAeScenes(f.project, f.scenes, f.assets).size, 0)
})
test('plan tampering, missing source evidence and unreviewed layers block submission', () => {
    const changes = [r => { r.plan.camera[1].scale = 2 }, r => { r.files.shift() }, r => { r.review.passed = false }, r => { r.review.critical_issues = ['seam'] }, r => { r.files[2].sha256 = 'bad' }, r => { r.review.input_fingerprint = 'old' }, r => { r.review.motion_supported = false }]
    for (const change of changes) {
        const f = fixture(); change(f.assets[2].metadata.result)
        assert.throws(() => preparedAeScenes(f.project, f.scenes, f.assets), /검수|원본/)
    }
})
