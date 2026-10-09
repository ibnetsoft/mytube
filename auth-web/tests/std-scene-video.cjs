const assert = require('node:assert/strict')
const test = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const ts = require('typescript')
const filename = path.resolve(__dirname, '../lib/stdSceneVideo.ts')
const mod = new Module(filename, module)
mod.filename = filename
mod.paths = Module._nodeModulePaths(path.dirname(filename))
mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename)
const { isWorkerSceneVideo, sceneVideoAssets, loadScenePreviewVideo, syncScenePreviewVideo } = mod.exports
const asset = (id, scene, metadata = {}, extra = {}) => ({ id, project_id: 'p', scene_number: scene, asset_type: 'video', status: 'uploaded', metadata, ...extra })

test('original clips stay distinct from all three worker output formats', () => {
    assert.equal(isWorkerSceneVideo(asset('original', 18)), false)
    for (const metadata of [{ ae_mouth_fingerprint: 'mouth' }, { lipsync_fingerprint: 'lip' }, { region_motion_plan_id: 'region' }, { postprocess_mode: 'after_effects' }]) {
        assert.equal(isWorkerSceneVideo(asset('worker', 25, metadata)), true)
    }
})
test('choose newest active scene video without mixing projects or replaced results', () => {
    const latest = asset('new', 25, { ae_mouth_fingerprint: 'new' }, { created_at: '2026-10-06' })
    const result = sceneVideoAssets([
        asset('old', 25, {}, { created_at: '2026-10-05' }), latest,
        asset('foreign', 25, {}, { project_id: 'other', created_at: '2026-10-09' }),
        asset('replaced', 25, {}, { status: 'replaced', created_at: '2026-10-09' }),
        asset('original', 18),
    ], 'p')
    assert.equal(result.get(25), latest)
    assert.equal(result.get(18).id, 'original')
    assert.equal(result.size, 2)
})
test('selected video resolves with authentication and abort signal, independently of the media queue', async () => {
    const previous = global.fetch
    const controller = new AbortController()
    try {
        global.fetch = async (url, options) => {
            assert.equal(url, '/api/std/projects/p/assets/file?assetId=air-25&delivery=url')
            assert.equal(options.headers.Authorization, 'Bearer test')
            assert.equal(options.signal, controller.signal)
            return Response.json({ url: 'https://storage.example/air25.mp4' })
        }
        const result = await loadScenePreviewVideo('p', 'air-25', { Authorization: 'Bearer test' }, controller.signal)
        assert.equal(result.url, 'https://storage.example/air25.mp4')
        result.revoke()
        global.fetch = async () => Response.json({ error: 'unauthorized' }, { status: 403 })
        await assert.rejects(loadScenePreviewVideo('p', 'air-25', {}, controller.signal), /403/)
        global.fetch = async () => Response.json({ url: 'javascript:alert(1)' })
        await assert.rejects(loadScenePreviewVideo('p', 'air-25', {}, controller.signal), /Invalid/)
    } finally { global.fetch = previous }
})
test('AIR preview seeks within the scene, continues playback, pauses and replays after the last frame', () => {
    const video = { duration: 14, readyState: 1, currentTime: 0, paused: true,
        play() { this.paused = false; return Promise.resolve() }, pause() { this.paused = true } }
    syncScenePreviewVideo(video, 215, 210, true)
    assert.equal(video.currentTime, 5)
    assert.equal(video.paused, false)
    syncScenePreviewVideo(video, 218, 210, false)
    assert.equal(video.currentTime, 8)
    assert.equal(video.paused, true)
    syncScenePreviewVideo(video, 225, 210, true)
    assert.equal(video.currentTime, 13.96)
    assert.equal(video.paused, true)
    syncScenePreviewVideo(video, 210, 210, true)
    assert.equal(video.currentTime, 0)
    assert.equal(video.paused, false)
})

test('original clips keep moving after their first pass and seek into later subtitles', () => {
    const video = { duration: 5, readyState: 1, currentTime: 0, paused: true,
        play() { this.paused = false; return Promise.resolve() }, pause() { this.paused = true } }
    // An eight-second offset is inside the second pass of a five-second clip.
    syncScenePreviewVideo(video, 108, 100, true, true)
    assert.equal(video.loop, true)
    assert.equal(video.currentTime, 3)
    assert.equal(video.paused, false)
    syncScenePreviewVideo(video, 110, 100, true, true)
    assert.equal(video.currentTime, 0)
    assert.equal(video.paused, false)
    syncScenePreviewVideo(video, 112, 100, false, true)
    assert.equal(video.currentTime, 2)
    assert.equal(video.paused, true)
    syncScenePreviewVideo(video, 112, 100, true, true)
    assert.equal(video.paused, false)
    // Entering the next scene starts its clip at zero.
    syncScenePreviewVideo(video, 114, 114, true, true)
    assert.equal(video.currentTime, 0)
})

test('unknown clip duration starts playback without an invalid seek and recovers on metadata', () => {
    const video = { duration: NaN, readyState: 0, currentTime: 0, paused: true,
        play() { this.paused = false; return Promise.resolve() }, pause() { this.paused = true } }
    syncScenePreviewVideo(video, 108, 100, true, true)
    assert.equal(video.currentTime, 0)
    assert.equal(video.paused, false)
    video.duration = 5
    video.readyState = 1
    syncScenePreviewVideo(video, 108, 100, true, true)
    assert.equal(video.currentTime, 3)
    assert.equal(video.paused, false)
})
