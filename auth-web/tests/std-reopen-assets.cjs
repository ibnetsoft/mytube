const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('../node_modules/typescript')
function loadLibrary(name) {
    const exports = {}
    new Function('exports', 'require', ts.transpile(fs.readFileSync(`lib/${name}.ts`, 'utf8'), { module: 1, target: 7 }))(exports, dep =>
        dep === './stdComic' ? { isComicProject: () => false } : dep.startsWith('./') ? loadLibrary(dep.slice(2)) : require(dep))
    return exports
}
function fixture({ missingVideo = false, failPage = false, activeRender = false, unauthorized = false } = {}) {
    const subtitle = { text: '어머니', voice_id: 'voice', scene_number: 5, start: 0, end: 3, dialogue_kind: 'dialogue', dialogue_speaker: '소녀' }
    const project = { id: 'p', project_payload: { ae_mouth: { enabled: true }, subtitles: [subtitle] } }
    const scenes = [{ scene_number: 5, scene_text: subtitle.text }]
    const assets = [
        { id: 'audio', asset_type: 'audio', status: 'assigned', metadata: { subtitle_timeline: [subtitle] } },
        ...Array.from({ length: 1263 }, (_, i) => ({ id: `other-${i}`, asset_type: 'other', status: 'uploaded', metadata: {} })),
        ...missingVideo ? [] : [{ id: 'original-5', asset_type: 'video', scene_number: 5, status: 'assigned', metadata: { gcs_path: 'clip.mp4' } }],
    ]
    const pages = [], prepared = []
    const db = { from(table) {
        const query = {
            select: () => query, eq: () => query, in: () => query, order: () => query,
            maybeSingle: async () => ({ data: project }),
            range: async (start, end) => {
                assert.equal(table, 'std_project_assets'); pages.push(start)
                return failPage && start === 1000 ? { error: { message: 'page failed' } } : { data: assets.slice(start, end + 1) }
            },
            // Model the capped REST response to reproduce the pre-fix Re path.
            then(resolve) { resolve({ data: table === 'std_project_scenes' ? scenes : assets.slice(0, 1000) }) },
        }
        return query
    } }
    const exports = {}
    new Function('exports', 'require', ts.transpile(fs.readFileSync('app/api/std/projects/[projectId]/reopen/route.ts', 'utf8'), { module: 1, target: 7 }))(exports, name => {
        if (name === 'next/server') return { NextResponse: { json: (body, options) => ({ body, status: options?.status || 200 }) } }
        if (name.includes('supabaseAdmin')) return { supabaseAdmin: db }
        if (name.includes('stdWeb')) return { requireStdUser: async () => unauthorized ? { ok: false, response: { status: 401 } } : { ok: true, requester: { email: 'owner@test' } } }
        if (name.includes('stdProjectAssets')) return loadLibrary('stdProjectAssets')
        if (name.includes('stdRenderQueue')) return { getStdProjectRenderHistory: async () => activeRender ? [{ id: 'running', status: 'rendering' }] : [], enqueueStdProjectRender: () => { throw Error('Unreviewed output must not render') } }
        if (name.includes('stdAeMouthQueue')) return { ensureAeMouthJob: async (p, s, a) => {
            const result = loadLibrary('stdAeMouth').aeMouthInput(p, s, a)
            prepared.push(result.input)
            return { ready: false, job: { id: 'queued' } }
        } }
        if (name.includes('stdAeMouth')) return loadLibrary('stdAeMouth')
        throw Error(name)
    })
    return { run: () => exports.POST({}, { params: { projectId: 'p' } }), pages, prepared }
}
test('Re route loads original scene 5 clip beyond the REST cap and passes real AE validation', async () => {
    const f = fixture(), result = await f.run()
    assert.equal(result.status, 202, JSON.stringify(result.body))
    assert.equal(result.body.postprocess_pending, true)
    assert.equal(f.prepared[0].scenes[0].original_video.id, 'original-5')
    assert.deepEqual(f.pages, [0, 500, 1000])
})
test('Re route still rejects truly missing original clips', async () => {
    const result = await fixture({ missingVideo: true }).run()
    assert.equal(result.status, 409)
    assert.match(result.body.error, /5번 대사 씬의 원본 영상/)
})
test('Re route does not proceed with incomplete pages', async () => {
    const f = fixture({ failPage: true }), result = await f.run()
    assert.equal(result.status, 409)
    assert.equal(result.body.error, 'page failed')
    assert.equal(f.prepared.length, 0)
})
test('Re route preserves authorization and duplicate-render guards', async () => {
    for (const [options, status] of [[{ unauthorized: true }, 401], [{ activeRender: true }, 409]]) {
        const f = fixture(options)
        assert.equal((await f.run()).status, status)
        assert.equal(f.pages.length, 0)
        assert.equal(f.prepared.length, 0)
    }
})
