const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const page = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
const helpers = {}
new Function('exports', ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../lib/stdSpeakerAssignment.ts'), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText)(helpers)

const row = (id, name, voiceId) => ({
    id, scene_number: id, text: `「台詞${id}。」`, start_num: id * 3, end_num: id * 3 + 2,
    voice_direction: `direction-${id}`, audio_asset_id: `recording-${id}`, audio_url: `/audio/${id}`, audio_duration: 2,
    ...(name ? { editor_speaker: { name, gender: 'male', text: `「台詞${id}。」` } } : {}),
    ...(voiceId ? { voice_id: voiceId, voice_name: `Saved ${voiceId}` } : {}),
})

function harness(rows, { characterVoices = {}, payload = {}, progress = {}, playing = true } = {}) {
    const state = { stale: [], saves: [], stops: 0, messages: [], ttsCalls: 0 }
    const context = {
        confirmSubtitleSpeaker: helpers.confirmSubtitleSpeaker,
        localSubtitles: rows,
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
    const from = page.indexOf('    const saveSubtitleSpeaker =')
    const to = page.indexOf('    const applySubtitleVolume =', from)
    assert.ok(from >= 0 && to > from, 'Speaker confirmation function must exist in the active web page')
    const compiled = ts.transpileModule(`${page.slice(from, to)}\nreturn saveSubtitleSpeaker`, {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    return { state, save: new Function(...Object.keys(context), compiled)(...Object.values(context)) }
}

function assertStrictSnapshot(state, original) {
    assert.equal(state.saves.length, 1)
    const { subtitles, options } = state.saves[0]
    assert.equal(options.strict, true)
    assert.ok(options.signal instanceof AbortSignal)
    assert.equal(options.signal.aborted, false)
    const editable = new Set(['voice_id', 'voice_name', 'editor_speaker'])
    const speech = item => Object.fromEntries(Object.entries(item).filter(([key]) => !editable.has(key)))
    subtitles.forEach((item, index) => assert.deepEqual(speech(item), speech(original[index]), 'Text, timing, direction and recording metadata stay intact'))
    assert.equal(state.ttsCalls, 0)
    return subtitles
}

test('confirming a pending speaker inherits the existing actor and invalidates only changed voices before strict saving', async () => {
    const rows = [row(8), row(31, '仙太郎'), row(60, '仙太郎', 'sentaro-actor'), row(61, 'お鈴', 'osuzu-actor')]
    const before = structuredClone(rows)
    const h = harness(rows)
    await h.save(0, '仙太郎', 'male')
    const saved = assertStrictSnapshot(h.state, before)
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
        const saved = assertStrictSnapshot(h.state, before)
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
    const saved = assertStrictSnapshot(h.state, rows)
    assert.deepEqual(saved.map(item => item.voice_id), ['explicit-actor', 'actor-a', 'actor-b', 'explicit-actor'])
    assert.deepEqual(h.state.stale.map(item => item.index), [0, 3])
    assert.equal(h.state.stops, 0, 'A paused preview does not need to be stopped')
    assert.equal(saved[0].voice_name, 'Explicit actor')
    assert.equal(saved[1].voice_name, rows[1].voice_name)
    assert.equal(saved[2].voice_name, rows[2].voice_name)
    assert.deepEqual(h.state.messages, [])
})
