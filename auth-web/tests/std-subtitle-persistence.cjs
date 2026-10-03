const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const { setImmediate: tick } = require('node:timers/promises')
const ts = require('typescript')

const source = fs.readFileSync(path.resolve(__dirname, '../lib/stdSubtitlePersistence.ts'), 'utf8')
const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleBox = { exports: {} }
new Function('exports', compiled)(moduleBox.exports)
const { createSubtitleSaveQueue } = moduleBox.exports
const CAS_ERROR = 'Project changed while saving; reload and retry'
const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer fixture-token' }
const response = (project, status = 200) => Response.json({ success: true, project }, { status })

function deferred() {
    let resolve, reject
    const promise = new Promise((done, fail) => { resolve = done; reject = fail })
    return { promise, resolve, reject }
}

test('later subtitle edits are saved after a slow earlier request and survive a server reload', async () => {
    const firstStarted = deferred()
    const releaseFirst = deferred()
    const patches = []
    let stored = { id: 'project-a', project_payload: { script: 'canonical script', subtitles: [], unrelated: { keep: true } } }
    const request = async (url, options = {}) => {
        assert.equal(url, '/api/std/projects/project-a')
        if (!options.method || options.method === 'GET') return response(structuredClone(stored))
        assert.equal(options.method, 'PATCH')
        assert.deepEqual(options.headers, headers)
        const patch = JSON.parse(options.body)
        patches.push(patch)
        if (patches.length === 1) {
            firstStarted.resolve()
            await releaseFirst.promise
        }
        stored = { ...stored, project_payload: { ...stored.project_payload, ...patch.project_payload } }
        return response(structuredClone(stored))
    }
    const save = createSubtitleSaveQueue(request)
    const old = { project_payload: { subtitles: [{ text: 'old text' }] } }
    const edited = { project_payload: { subtitles_saved: true, subtitles: [{
        text: '「ここで待っている。」', scene_number: 4, start_time: 18.25, end_time: 21.5,
        editor_speaker: { name: 'お鈴', gender: 'female', text: '「ここで待っている。」' },
        dialogue_override: true, dialogue_speaker: 'お鈴',
        voice_id: 'voice-osuzu', voice_name: 'オスズ', voice_direction: '穏やかに',
        audio_asset_id: 'recording-1', audio_url: '/api/std/assets/audio/recording-1', audio_duration: 3.25,
        audio_start: 1.1, audio_end: 4.35, recorded_text: 'ここで待っている。',
    }] } }
    const expected = structuredClone(edited.project_payload)
    const earlier = save('project-a', old, headers)
    await firstStarted.promise
    const later = save('project-a', edited, headers)
    edited.project_payload.subtitles[0].text = 'mutable UI changed after enqueue'
    await tick()
    assert.equal(patches.length, 1, 'A second request must wait for the first response')
    releaseFirst.resolve()
    const [firstConfirmed, lastConfirmed] = await Promise.all([earlier, later])
    assert.equal(firstConfirmed.project_payload.subtitles[0].text, 'old text')
    assert.deepEqual(lastConfirmed.project_payload.subtitles, expected.subtitles)
    const reloaded = await (await request('/api/std/projects/project-a')).json()
    assert.deepEqual(reloaded.project.project_payload.subtitles, expected.subtitles)
    assert.equal(reloaded.project.project_payload.subtitles_saved, true)
    assert.deepEqual(reloaded.project.project_payload.unrelated, { keep: true })
    assert.equal(reloaded.project.project_payload.script, 'canonical script')
    assert.equal(patches.length, 2)
})

test('only the exact optimistic-lock conflict retries, up to three attempts', async () => {
    let attempts = 0
    const sent = []
    const save = createSubtitleSaveQueue(async (_, options) => {
        sent.push(options.body)
        return ++attempts < 3
            ? Response.json({ success: false, error: CAS_ERROR }, { status: 409 })
            : response({ id: 'project-a' })
    })
    assert.deepEqual(await save('project-a', { project_payload: { subtitles: [{ text: 'edited' }] } }, headers), { id: 'project-a' })
    assert.equal(attempts, 3)
    assert.equal(new Set(sent).size, 1, 'Retries must send the same captured subtitle snapshot')

    let failedAttempts = 0
    const exhausted = createSubtitleSaveQueue(async () => {
        failedAttempts++
        return failedAttempts <= 3
            ? Response.json({ success: false, error: CAS_ERROR }, { status: 409 })
            : response({ id: 'project-a' })
    })
    await assert.rejects(exhausted('project-a', {}, headers), new RegExp(CAS_ERROR))
    assert.equal(failedAttempts, 3)
    assert.equal((await exhausted('project-a', {}, headers)).id, 'project-a')
    assert.equal(failedAttempts, 4, 'Exhausting retries must leave the queue usable')
})

test('locked projects and other HTTP errors reject once without reporting a saved project', async () => {
    for (const [status, error] of [[409, 'Project is not editable'], [409, 'Another conflict'], [500, 'Storage unavailable']]) {
        let calls = 0
        const save = createSubtitleSaveQueue(async () => {
            calls++
            return Response.json({ success: false, error }, { status })
        })
        await assert.rejects(save('project-a', {}, headers), new RegExp(error))
        assert.equal(calls, 1)
    }
})

test('unsuccessful or mismatched confirmations reject, and a later queued save still succeeds', async () => {
    for (const invalid of [
        { success: false, project: { id: 'project-a' } },
        { success: true, project: { id: 'another-project' } },
        { success: true },
    ]) {
        let calls = 0
        const save = createSubtitleSaveQueue(async () => ++calls === 1
            ? Response.json(invalid)
            : response({ id: 'project-a', saved: true }))
        const rejected = assert.rejects(save('project-a', {}, headers), /Subtitle save failed/)
        const next = save('project-a', {}, headers)
        await rejected
        assert.deepEqual(await next, { id: 'project-a', saved: true })
        assert.equal(calls, 2)
    }
})

test('network failures do not poison subsequent saves in the same project', async () => {
    let calls = 0
    const save = createSubtitleSaveQueue(async () => {
        if (++calls === 1) throw new Error('Network offline')
        return response({ id: 'project-a' })
    })
    const rejected = assert.rejects(save('project-a', {}, headers), /Network offline/)
    const next = save('project-a', {}, headers)
    await rejected
    assert.equal((await next).id, 'project-a')
})

test('different projects save in parallel while each keeps its own queue', async () => {
    const release = deferred()
    const calls = []
    const save = createSubtitleSaveQueue(async url => {
        calls.push(url)
        await release.promise
        return response({ id: decodeURIComponent(url.split('/').at(-1)) })
    })
    const a = save('project-a', {}, headers)
    const b = save('project-b', {}, headers)
    await tick()
    assert.deepEqual(calls, ['/api/std/projects/project-a', '/api/std/projects/project-b'])
    release.resolve()
    assert.deepEqual((await Promise.all([a, b])).map(project => project.id), ['project-a', 'project-b'])
})

test('a save aborted while queued never sends its stale snapshot and does not block the next save', async () => {
    const release = deferred()
    const started = deferred()
    const calls = []
    const save = createSubtitleSaveQueue(async (_, options) => {
        calls.push(JSON.parse(options.body).version)
        if (calls.length === 1) { started.resolve(); await release.promise }
        return response({ id: 'project-a' })
    })
    const first = save('project-a', { version: 1 }, headers)
    await started.promise
    const controller = new AbortController()
    const aborted = assert.rejects(save('project-a', { version: 2 }, headers, controller.signal), { name: 'AbortError' })
    const next = save('project-a', { version: 3 }, headers)
    controller.abort()
    release.resolve()
    await Promise.all([first, aborted, next])
    assert.deepEqual(calls, [1, 3])
})

test('aborting an active request rejects confirmation and forwards the signal to fetch', async () => {
    const started = deferred()
    const controller = new AbortController()
    const save = createSubtitleSaveQueue((_, options) => {
        assert.equal(options.signal, controller.signal)
        started.resolve()
        return new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true }))
    })
    const aborted = assert.rejects(save('project-a', {}, headers, controller.signal), { name: 'AbortError' })
    await started.promise
    controller.abort()
    await aborted
})
