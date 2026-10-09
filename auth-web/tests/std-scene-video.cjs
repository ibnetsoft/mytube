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
const { isWorkerSceneVideo, sceneVideoAssets, loadScenePreviewVideo, syncScenePreviewVideo, syncScenePreviewPlayback, sceneClipTailStyle } = mod.exports
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
            assert.equal(url, '/api/std/projects/p/assets/file?assetId=air-25')
            assert.equal(options.headers.Authorization, 'Bearer test')
            assert.equal(options.signal, controller.signal)
            return new Response(new Blob(['video-bytes'], { type: 'video/mp4' }))
        }
        const result = await loadScenePreviewVideo('p', 'air-25', { Authorization: 'Bearer test' }, controller.signal)
        assert.match(result.url, /^blob:/)
        result.revoke()
        global.fetch = async () => Response.json({ error: 'unauthorized' }, { status: 403 })
        await assert.rejects(loadScenePreviewVideo('p', 'air-25', {}, controller.signal), /403/)
        global.fetch = async () => Response.json({ url: 'javascript:alert(1)' })
        await assert.rejects(loadScenePreviewVideo('p', 'air-25', {}, controller.signal), /Invalid/)
    } finally { global.fetch = previous }
})
test('AIR preview seeks within the scene, continues playback, pauses and replays after the last frame', () => {
    const video = { duration: 14, readyState: 4, currentTime: 0, paused: true,
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

test('original clips hold their last frame, then zoom only during the remaining scene time', () => {
    const video = { duration: 5, readyState: 4, currentTime: 0, paused: true,
        play() { this.paused = false; return Promise.resolve() }, pause() { this.paused = true } }
    syncScenePreviewVideo(video, 103, 100, true)
    assert.equal(video.currentTime, 3)
    assert.equal(video.paused, false)
    assert.equal(sceneClipTailStyle(103, 100, 115, 5).transform, 'scale(1)')
    assert.equal(sceneClipTailStyle(105, 100, 115, 5).transform, 'scale(1)')
    syncScenePreviewVideo(video, 110, 100, true)
    assert.equal(video.loop, false)
    assert.equal(video.currentTime, 4.96)
    assert.equal(video.paused, true)
    assert.equal(sceneClipTailStyle(110, 100, 115, 5).transform, 'scale(1.01)')
    assert.equal(sceneClipTailStyle(115, 100, 115, 5).transform, 'scale(1.02)')
    assert.equal(sceneClipTailStyle(200, 100, 115, 5).transform, 'scale(1.02)')
    // Scrubbing back restarts the video and removes the tail zoom.
    syncScenePreviewVideo(video, 102, 100, true)
    assert.equal(video.currentTime, 2)
    assert.equal(video.paused, false)
    assert.equal(sceneClipTailStyle(102, 100, 115, 5).transform, 'scale(1)')
    // Next scene does not inherit the previous scene's zoom.
    assert.equal(sceneClipTailStyle(115, 115, 125, 5).transform, 'scale(1)')
})

test('no tail zoom for unknown duration or a clip covering the entire scene', () => {
    for (const duration of [0, NaN, Infinity, 15, 20]) {
        assert.equal(sceneClipTailStyle(115, 100, 115, duration).transform, 'scale(1)')
    }
})

function media(extra = {}) {
    return { duration: 6, readyState: 4, currentTime: 0, paused: true, seeking: false,
        play() { this.paused = false; return Promise.resolve() }, pause() { this.paused = true }, ...extra }
}
test('a seek in progress is not restarted on every narration tick', () => {
    let seeks = 0
    const video = media()
    let position = 0
    Object.defineProperty(video, 'currentTime', { get: () => position, set(value) { position = value; seeks++; video.seeking = true } })
    assert.equal(syncScenePreviewVideo(video, 2, 0, true), false)
    for (const time of [2.1, 2.5, 3, 4]) assert.equal(syncScenePreviewVideo(video, time, 0, true), false)
    assert.equal(seeks, 1)
    video.seeking = false
    assert.equal(syncScenePreviewVideo(video, 2, 0, true), true)
    assert.equal(video.paused, false)
})
test('scene loading pauses narration and resumes the same clock when video is ready', () => {
    const audio = media({ paused: false })
    const state = { audio: null }
    assert.equal(syncScenePreviewPlayback(null, audio, 7, 7, true, true, state), true)
    assert.equal(audio.paused, true)
    const video = media({ readyState: 1 })
    assert.equal(syncScenePreviewPlayback(video, audio, 7, 7, true, true, state), true)
    assert.equal(video.currentTime, 0)
    video.readyState = 4
    assert.equal(syncScenePreviewPlayback(video, audio, 7, 7, true, true, state), false)
    assert.equal(audio.paused, false)
    assert.equal(video.paused, false)
    assert.equal(state.audio, null)
    assert.equal(syncScenePreviewPlayback(video, audio, 15, 7, true, true, state), false)
    assert.equal(video.currentTime, 5.96)
    assert.equal(video.paused, true)
    assert.equal(audio.paused, false, 'Narration continues over the last-frame zoom')
})
test('video cannot run ahead while narration is loading or restart audio after Stop', () => {
    const video = media()
    const state = { audio: null }
    syncScenePreviewPlayback(video, null, 0, 0, true, true, state)
    assert.equal(video.paused, true)
    const audio = media({ paused: false })
    syncScenePreviewPlayback(null, audio, 0, 0, true, true, state)
    syncScenePreviewPlayback(video, audio, 0, 0, false, true, state)
    assert.equal(audio.paused, true)
    assert.equal(state.audio, null)
    const nextAudio = media()
    state.audio = audio
    syncScenePreviewPlayback(video, nextAudio, 0, 0, true, true, state)
    assert.equal(audio.paused, true)
    assert.equal(nextAudio.paused, true)
})
