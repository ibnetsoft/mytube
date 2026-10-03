const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const { setImmediate: tick } = require('node:timers/promises')
const ts = require('typescript')

const page = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
const modules = new Map()
function load(filename) {
    if (modules.has(filename)) return modules.get(filename)
    const exports = {}
    modules.set(filename, exports)
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    new Function('exports', 'require', compiled)(exports, name => load(path.resolve(path.dirname(filename), `${name}.ts`)))
    return exports
}
const helpers = load(path.resolve(__dirname, '../lib/stdSpeakerAssignment.ts'))
const { mapDialogueAnnotations } = load(path.resolve(__dirname, '../lib/stdDialogueAnnotations.ts'))
const { createSubtitleSaveQueue } = load(path.resolve(__dirname, '../lib/stdSubtitlePersistence.ts'))
const { restoreSavedSubtitleSnapshot } = load(path.resolve(__dirname, '../lib/stdSubtitleSnapshot.ts'))

const row = (id, name, voiceId) => ({
    id, scene_number: id, text: `「台詞${id}。」`, start_num: id * 3, end_num: id * 3 + 2,
    voice_direction: `direction-${id}`, audio_asset_id: `recording-${id}`, audio_url: `/audio/${id}`, audio_duration: 2,
    ...(name ? { editor_speaker: { name, gender: 'male', text: `「台詞${id}。」` } } : {}),
    ...(voiceId ? { voice_id: voiceId, voice_name: `Saved ${voiceId}` } : {}),
})

function extract(start, end, result, context) {
    const from = page.indexOf(start)
    const to = page.indexOf(end, from)
    assert.ok(from >= 0 && to > from, `Active web page function missing: ${start}`)
    const compiled = ts.transpileModule(`${page.slice(from, to)}\nreturn ${result}`, {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    return new Function(...Object.keys(context), compiled)(...Object.values(context))
}

function harness(rows, { characterVoices = {}, payload = {}, progress = {}, playing = true } = {}) {
    const state = { stale: [], saves: [], stops: 0, messages: [], ttsCalls: 0 }
    const context = {
        confirmSubtitleSpeaker: helpers.confirmSubtitleSpeaker,
        subtitleSpeaker: helpers.subtitleSpeaker, mapDialogueAnnotations, speakerCharacters: [], speakerNameTranslations: {},
        localSubtitles: rows,
        speechSubtitlesRef: { current: rows },
        subtitleSpeakers: rows.map(item => item.dialogue_override === false ? null : helpers.subtitleSpeaker(item, undefined, [])),
        selectedProject: { project: { id: 'project-a', project_payload: payload, progress_payload: progress } },
        characterVoices, selectedVoice: 'narrator', currentLocale: 'ko', isPlayingPreview: playing,
        voiceNameById: new Map([['sentaro-actor', 'Sentaro actor'], ['explicit-actor', 'Explicit actor']]),
        stopVrewPlayback: () => { state.stops++ },
        markVrewSegmentStale: (item, index) => state.stale.push({ item, index }),
        persistVrewVoiceSubtitles: async (subtitles, options) => { state.saves.push({ subtitles, options }); return true },
        setMessage: message => state.messages.push(message),
        generateTts: () => { state.ttsCalls++ },
        handleFinalizeSubtitlesAndTts: () => { state.ttsCalls++ },
    }
    return { state, save: extract('    const saveSubtitleSpeaker =', '    const applySubtitleVolume =', 'saveSubtitleSpeaker', context) }
}

function assertBackgroundSnapshot(state, original) {
    assert.equal(state.saves.length, 1)
    const { subtitles, options } = state.saves[0]
    assert.notEqual(options?.strict, true, 'Background persistence handles failure without an unhandled rejection')
    const editable = new Set(['voice_id', 'voice_name', 'editor_speaker'])
    const speech = item => Object.fromEntries(Object.entries(item).filter(([key]) => !editable.has(key)))
    subtitles.forEach((item, index) => assert.deepEqual(speech(item), speech(original[index]), 'Text, timing, direction and recording metadata stay intact'))
    assert.equal(state.ttsCalls, 0)
    return subtitles
}

test('confirming a pending speaker inherits the existing actor and invalidates only changed voices before background saving', async () => {
    const rows = [row(8), row(31, '仙太郎'), row(60, '仙太郎', 'sentaro-actor'), row(61, 'お鈴', 'osuzu-actor')]
    const before = structuredClone(rows)
    const h = harness(rows)
    await h.save(0, '仙太郎', 'male')
    const saved = assertBackgroundSnapshot(h.state, before)
    assert.deepEqual(saved.map(item => item.voice_id), ['sentaro-actor', 'sentaro-actor', 'sentaro-actor', 'osuzu-actor'])
    assert.deepEqual(h.state.stale.map(item => item.index), [0, 1])
    assert.equal(h.state.stops, 1)
    for (const index of [0, 1, 2]) assert.deepEqual(saved[index].editor_speaker, { name: '仙太郎', gender: 'male', text: before[index].text })
    h.state.stale.forEach(entry => assert.equal(entry.item, saved[entry.index]))
    assert.deepEqual(rows, before, 'Confirming never mutates the input rows')
    assert.deepEqual(h.state.messages, [])
})

test('no donor and conflicting donors save attribution without changing voices, recordings or playback', async () => {
    for (const conflict of [false, true]) {
        const rows = conflict
            ? [row(8, undefined, 'target-current'), row(31, '仙太郎', 'actor-a'), row(60, '仙太郎', 'actor-b')]
            : [row(8, undefined, 'target-current'), row(31, 'お鈴', 'other-actor')]
        const before = structuredClone(rows)
        const h = harness(rows)
        await h.save(0, '仙太郎', 'male')
        const saved = assertBackgroundSnapshot(h.state, before)
        assert.deepEqual(saved.map(item => item.voice_id), before.map(item => item.voice_id))
        assert.deepEqual(saved[0].editor_speaker, { name: '仙太郎', gender: 'male', text: before[0].text })
        assert.deepEqual(h.state.stale, [])
        assert.equal(h.state.stops, 0)
        assert.equal(h.state.messages.length, conflict ? 1 : 0)
        if (conflict) assert.match(h.state.messages[0], /서로 다른 성우/)
    }
})

test('the explicit current-project map wins over conflicting peers and saved maps while preserving assigned peers', async () => {
    const rows = [row(8), row(31, '仙太郎', 'actor-a'), row(60, '仙太郎', 'actor-b'), row(61, '仙太郎')]
    const h = harness(rows, {
        characterVoices: { '仙太郎': 'explicit-actor' },
        payload: { voice_map: { '仙太郎': 'old-saved-actor' }, voice_id: 'narrator' },
        progress: { voice_map: { '仙太郎': 'old-progress-actor' }, voice_id: 'narrator' },
        playing: false,
    })
    await h.save(0, '仙太郎', 'male')
    const saved = assertBackgroundSnapshot(h.state, rows)
    assert.deepEqual(saved.map(item => item.voice_id), ['explicit-actor', 'actor-a', 'actor-b', 'explicit-actor'])
    assert.deepEqual(h.state.stale.map(item => item.index), [0, 3])
    assert.equal(h.state.stops, 0, 'A paused preview does not need to be stopped')
    assert.equal(saved[0].voice_name, 'Explicit actor')
    assert.equal(saved[1].voice_name, rows[1].voice_name)
    assert.equal(saved[2].voice_name, rows[2].voice_name)
    assert.deepEqual(h.state.messages, [])
})

function backgroundHarness() {
    const initial = [row(8), row(10), row(31, '仙太郎', 'sentaro-actor'), row(60, 'お鈴', 'osuzu-actor')]
    const selectedProject = { project: { id: 'project-a', project_payload: { subtitles: initial } }, scenes: [] }
    const state = { local: initial, project: selectedProject, saveState: 'saved', saved: true, requests: [], remembered: [], messages: [], pending: [] }
    const speechSubtitlesRef = { current: initial }
    const context = {
        selectedProject, speechSubtitlesRef,
        subtitleActiveProjectRef: { current: 'project-a' }, subtitleSaveRevisionRef: { current: 0 },
        subtitleTextSaveTimerRef: { current: null }, subtitleStyleSaveTimerRef: { current: null },
        authedJsonHeaders: { Authorization: 'Bearer fixture' }, currentLocale: 'ko',
        restoreSavedSubtitleSnapshot,
        saveSubtitleProject: createSubtitleSaveQueue((url, options) => new Promise(resolve => {
            state.requests.push({ url, ...options, body: JSON.parse(options.body), resolve })
        })),
        setLocalSubtitles: value => { state.local = value },
        setIsSubtitleSaved: value => { state.saved = value },
        setSubtitleSaveState: value => { state.saveState = value },
        setMessage: message => state.messages.push(message),
        setSelectedProject: update => { state.project = typeof update === 'function' ? update(state.project) : update },
        rememberProjectState: value => state.remembered.push(value),
    }
    const actions = extract('    const updateSubtitleDraft =', '    const scheduleSubtitleTextSave =',
        '{ updateSubtitleDraft, persistVrewVoiceSubtitles }', context)
    const save = extract('    const saveSubtitleSpeaker =', '    const applySubtitleVolume =', 'saveSubtitleSpeaker', {
        ...context, ...helpers, mapDialogueAnnotations, speakerCharacters: [], speakerNameTranslations: {},
        // Leave the render's rows unchanged to exercise back-to-back edits before React renders again.
        localSubtitles: initial, subtitleSpeakers: initial.map(item => helpers.subtitleSpeaker(item, undefined, [])),
        characterVoices: {}, selectedVoice: 'narrator', isPlayingPreview: false,
        voiceNameById: new Map([['sentaro-actor', 'Sentaro actor'], ['osuzu-actor', 'Osuzu actor']]),
        stopVrewPlayback: () => {}, markVrewSegmentStale: () => {},
        persistVrewVoiceSubtitles: (...args) => {
            const pending = actions.persistVrewVoiceSubtitles(...args)
            state.pending.push(pending)
            return pending
        },
    })
    const handleSaveSubtitles = extract('    const handleSaveSubtitles =', '    const openProject =', 'handleSaveSubtitles', {
        ...context, ...actions, matchSubtitlesToSceneVisuals: subtitles => subtitles,
        subtitleRenderSettings: () => ({}),
    })
    function respond(index, success) {
        const request = state.requests[index]
        request.resolve(Response.json(success ? { success: true, project: {
            ...selectedProject.project,
            project_payload: { ...selectedProject.project.project_payload, ...request.body.project_payload },
            progress_payload: request.body.progress_payload,
        } } : { success: false, error: 'Storage unavailable' }, { status: success ? 200 : 500 }))
    }
    return { state, save, handleSaveSubtitles, respond, speechSubtitlesRef }
}

test('speaker confirmation returns immediately and keeps two rapid edits in the serialized background saves', async () => {
    const h = backgroundHarness()
    assert.equal(h.save(0, '仙太郎', 'male'), undefined, 'The modal can close without awaiting a response')
    assert.equal(h.state.local[0].editor_speaker.name, '仙太郎', 'Confirmed identity appears immediately')
    assert.equal(h.state.local[0].voice_id, 'sentaro-actor', 'Inherited voice appears immediately')
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'saving')
    assert.deepEqual(h.state.remembered, [], 'An optimistic draft is never cached as confirmed')
    await tick()
    assert.equal(h.state.requests.length, 1)

    assert.equal(h.save(1, 'お鈴', 'female'), undefined)
    assert.equal(h.state.local[0].editor_speaker.name, '仙太郎', 'The second confirmation preserves the first draft')
    assert.equal(h.state.local[1].editor_speaker.name, 'お鈴')
    assert.equal(h.state.local[1].voice_id, 'osuzu-actor')
    await tick()
    assert.equal(h.state.requests.length, 1, 'The second snapshot waits behind the first request')
    h.respond(0, true)
    assert.equal(await h.state.pending[0], true)
    await tick()
    assert.equal(h.state.requests.length, 2)
    assert.equal(h.state.saved, false, 'An earlier response cannot mark the newer confirmation saved')
    assert.equal(h.state.saveState, 'saving')
    const queued = h.state.requests[1].body.project_payload.subtitles
    assert.deepEqual(queued.slice(0, 2).map(item => [item.editor_speaker.name, item.voice_id]), [
        ['仙太郎', 'sentaro-actor'], ['お鈴', 'osuzu-actor'],
    ])
    h.respond(1, true)
    assert.equal(await h.state.pending[1], true)
    assert.equal(h.state.saved, true)
    assert.equal(h.state.saveState, 'saved')
    assert.deepEqual(h.state.project.project.project_payload.subtitles, h.state.local)
})

test('background failure retains the confirmed speaker and voice for retry with the ordinary subtitle save button', async () => {
    const h = backgroundHarness()
    assert.equal(h.save(0, '仙太郎', 'male'), undefined)
    await tick()
    h.respond(0, false)
    assert.equal(await h.state.pending[0], false, 'Non-strict background persistence handles rejection')
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'error')
    assert.equal(h.state.local[0].editor_speaker.name, '仙太郎')
    assert.equal(h.speechSubtitlesRef.current[0].voice_id, 'sentaro-actor')
    assert.deepEqual(h.state.remembered, [])
    assert.match(h.state.messages.at(-1), /저장하지 못했습니다/)
    assert.match(h.state.messages.at(-1), /다시 시도/)
    const retry = h.handleSaveSubtitles()
    await tick()
    assert.deepEqual(h.state.requests[1].body.project_payload.subtitles, h.state.local)
    h.respond(1, true)
    assert.equal(await retry, true)
    assert.equal(h.state.saveState, 'saved')
    assert.equal(h.state.saved, true)
    assert.equal(h.state.project.project.project_payload.subtitles[0].editor_speaker.name, '仙太郎')
    assert.equal(h.state.project.project.project_payload.subtitles[0].voice_id, 'sentaro-actor')
})

test('an obsolete background failure does not show an error when a newer complete snapshot is queued', async () => {
    const h = backgroundHarness()
    h.save(0, '仙太郎', 'male')
    await tick()
    h.save(1, 'お鈴', 'female')
    h.respond(0, false)
    assert.equal(await h.state.pending[0], false)
    await tick()
    assert.equal(h.state.requests.length, 2, 'A failed request does not block the next queued save')
    assert.equal(h.state.saveState, 'saving')
    assert.deepEqual(h.state.messages, [], 'The newer queued snapshot already contains both confirmations')
    h.respond(1, true)
    assert.equal(await h.state.pending[1], true)
    assert.equal(h.state.saved, true)
    assert.equal(h.state.saveState, 'saved')
    assert.deepEqual(h.state.messages, [])
    assert.deepEqual(h.state.project.project.project_payload.subtitles.slice(0, 2).map(item => item.editor_speaker.name), ['仙太郎', 'お鈴'])
})
