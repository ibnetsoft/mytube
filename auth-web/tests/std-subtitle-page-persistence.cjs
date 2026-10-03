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
const { createSubtitleSaveQueue } = load(path.resolve(__dirname, '../lib/stdSubtitlePersistence.ts'))
const { restoreSavedSubtitleSnapshot } = load(path.resolve(__dirname, '../lib/stdSubtitleSnapshot.ts'))

function extract(start, end, result, context) {
    const from = page.indexOf(start)
    const to = page.indexOf(end, from)
    assert.ok(from >= 0 && to > from, `Page function boundaries missing: ${start}`)
    const compiled = ts.transpileModule(`${page.slice(from, to)}\nreturn ${result}`, {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    return new Function(...Object.keys(context), compiled)(...Object.values(context))
}

const rows = text => [{
    text, scene_number: 4, start_num: 12.5, end_num: 15.75, start_time: '12.5', end_time: '15.75',
    editor_speaker: { name: 'お鈴', gender: 'female', text }, dialogue_override: true, dialogue_speaker: 'お鈴',
    voice_id: 'character-voice', voice_name: 'Osuzu', voice_direction: 'calm',
    audio_asset_id: 'recording-4', audio_url: '/audio/recording-4', audio_duration: 3.25,
}]

function harness() {
    const initialRows = rows('元の字幕')
    const selectedProject = {
        project: { id: 'project-a', project_payload: { subtitles: initialRows, render_settings: { existing_setting: 'keep' } } },
        scenes: [{ scene_number: 4, image_url: '/scene-4.png', video_url: '/scene-4.mp4' }],
    }
    const state = { local: initialRows, project: selectedProject, saved: true, saveState: 'saved', flags: [], messages: [], remembered: [], requests: [], ttsCalls: 0 }
    const speechSubtitlesRef = { current: initialRows }
    const subtitleSaveRevisionRef = { current: 0 }
    const subtitleActiveProjectRef = { current: 'project-a' }
    const subtitleTextSaveTimerRef = { current: null }
    const subtitleStyleSaveTimerRef = { current: null }
    const saveSubtitleProject = createSubtitleSaveQueue((url, options) => new Promise((resolve, reject) => {
        state.requests.push({ url, ...options, body: JSON.parse(options.body), resolve, reject })
    }))
    const context = {
        selectedProject, speechSubtitlesRef, subtitleSaveRevisionRef, subtitleActiveProjectRef, subtitleTextSaveTimerRef,
        subtitleStyleSaveTimerRef,
        restoreSavedSubtitleSnapshot, saveSubtitleProject, authedJsonHeaders: { Authorization: 'Bearer fixture' }, currentLocale: 'ko',
        setLocalSubtitles: value => { state.local = value },
        setIsSubtitleSaved: value => { state.saved = value; state.flags.push(value) },
        setSubtitleSaveState: value => { state.saveState = value },
        setMessage: value => state.messages.push(value),
        setSelectedProject: value => { state.project = typeof value === 'function' ? value(state.project) : value },
        rememberProjectState: value => state.remembered.push(value),
        generateTts: () => { state.ttsCalls++ },
        handleFinalizeSubtitlesAndTts: () => { state.ttsCalls++ },
        syncSubtitleTimingsToNarration: () => { state.ttsCalls++ },
    }
    const actions = extract('    const updateSubtitleDraft =', '    const scheduleSubtitleTextSave =',
        '{ updateSubtitleDraft, persistVrewVoiceSubtitles }', context)
    const matchSubtitlesToSceneVisuals = extract('    const matchSubtitlesToSceneVisuals =', '    const subtitleHasValidTiming =',
        'matchSubtitlesToSceneVisuals', {
            selectedProject, restoreSavedSubtitleSnapshot,
            subtitleSceneVisual: (subtitle, index, scenes) => scenes.find(scene => scene.scene_number === subtitle.scene_number),
        })
    const handleSaveSubtitles = extract('    const handleSaveSubtitles =', '    const openProject =', 'handleSaveSubtitles', {
        ...context, ...actions, matchSubtitlesToSceneVisuals,
        subtitleRenderSettings: () => ({ subtitle_font_family: 'NanumSquare', subtitle_font_size: 5.4 }),
    })
    function confirm(index) {
        const request = state.requests[index]
        request.resolve(Response.json({ success: true, project: {
            ...selectedProject.project,
            project_payload: { ...selectedProject.project.project_payload, ...request.body.project_payload },
            progress_payload: request.body.progress_payload,
        } }))
    }
    function fail(index, message = 'Storage unavailable') {
        state.requests[index].resolve(Response.json({ success: false, error: message }, { status: 500 }))
    }
    return { state, ...actions, handleSaveSubtitles, confirm, fail, speechSubtitlesRef, subtitleSaveRevisionRef, subtitleStyleSaveTimerRef }
}

test('editing becomes dirty and only a confirmed server response marks subtitles saved', async () => {
    const h = harness()
    const edited = rows('編集した字幕')
    h.updateSubtitleDraft(edited)
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'dirty')
    assert.equal(h.speechSubtitlesRef.current, edited)
    const pending = h.persistVrewVoiceSubtitles(edited)
    await tick()
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'saving')
    assert.deepEqual(h.state.remembered, [])
    assert.equal(h.state.project.project.project_payload.subtitles[0].text, '元の字幕')
    h.confirm(0)
    assert.equal(await pending, true)
    assert.equal(h.state.saved, true)
    assert.equal(h.state.saveState, 'saved')
    assert.deepEqual(h.state.project.project.project_payload.subtitles, edited)
    assert.equal(h.state.remembered.length, 1)
})

test('an earlier response never marks a newer unsaved draft as saved or replaces its local rows', async () => {
    const h = harness()
    const first = h.persistVrewVoiceSubtitles(rows('先の編集'))
    await tick()
    const latest = rows('後の未保存の編集')
    h.updateSubtitleDraft(latest)
    const flagsBeforeResponse = h.state.flags.length
    h.confirm(0)
    assert.equal(await first, true)
    assert.equal(h.state.local, latest)
    assert.equal(h.speechSubtitlesRef.current, latest)
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'dirty')
    assert.equal(h.state.flags.length, flagsBeforeResponse)
})

test('an earlier response cannot finish the saved indicator while a newer save is queued', async () => {
    const h = harness()
    const first = h.persistVrewVoiceSubtitles(rows('先の編集'))
    await tick()
    const latest = rows('次の編集')
    const next = h.persistVrewVoiceSubtitles(latest)
    h.confirm(0)
    await first
    await tick()
    assert.equal(h.state.requests.length, 2)
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'saving')
    assert.deepEqual(h.state.local, latest)
    h.confirm(1)
    assert.equal(await next, true)
    assert.equal(h.state.saved, true)
    assert.deepEqual(h.state.project.project.project_payload.subtitles, latest)
})

test('a confirmed voice save stays dirty while a newer style save is pending', async () => {
    const h = harness()
    const edited = rows('音声設定を変えた字幕')
    const pending = h.persistVrewVoiceSubtitles(edited)
    await tick()
    h.subtitleStyleSaveTimerRef.current = 123
    h.confirm(0)
    assert.equal(await pending, true)
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'dirty')
    assert.deepEqual(h.state.local, edited)
    assert.deepEqual(h.speechSubtitlesRef.current, edited)
})

test('save failure retains edited text and metadata, reports failure and never caches it as confirmed', async () => {
    const h = harness()
    const edited = rows('保存に失敗しても残る字幕')
    const pending = h.persistVrewVoiceSubtitles(edited)
    await tick()
    h.fail(0)
    assert.equal(await pending, false)
    assert.deepEqual(h.state.local, edited)
    assert.deepEqual(h.speechSubtitlesRef.current, edited)
    assert.equal(h.state.saved, false)
    assert.equal(h.state.saveState, 'error')
    assert.match(h.state.messages.at(-1), /저장하지 못했습니다/)
    assert.deepEqual(h.state.remembered, [])
    assert.equal(h.state.project.project.project_payload.subtitles[0].text, '元の字幕')
})

test('strict save propagates failure without a success message or losing the local draft', async () => {
    const h = harness()
    const edited = rows('手動保存の変更')
    h.updateSubtitleDraft(edited)
    const rejected = assert.rejects(h.handleSaveSubtitles(), /Storage unavailable/)
    await tick()
    h.fail(0)
    await rejected
    assert.equal(h.state.saveState, 'error')
    assert.equal(h.state.saved, false)
    assert.equal(h.state.local[0].text, edited[0].text)
    assert.ok(!h.state.messages.some(message => message === '자막 변경 내용을 저장했습니다.'))
    assert.equal(h.state.ttsCalls, 0)
})

test('manual save persists current edited rows, metadata and render settings without invoking TTS', async () => {
    const h = harness()
    const edited = rows('手動保存する字幕')
    h.updateSubtitleDraft(edited)
    const pending = h.handleSaveSubtitles()
    await tick()
    assert.equal(h.state.requests.length, 1)
    const request = h.state.requests[0]
    assert.equal(request.url, '/api/std/projects/project-a')
    assert.equal(request.method, 'PATCH')
    assert.deepEqual(request.body.project_payload.subtitles, edited.map(row => ({ ...row, image_url: '/scene-4.png', video_url: '/scene-4.mp4' })))
    assert.deepEqual(request.body.project_payload.render_settings, {
        existing_setting: 'keep', subtitle_font_family: 'NanumSquare', subtitle_font_size: 5.4,
    })
    assert.deepEqual(request.body.progress_payload, { subtitles_saved: true, subtitles_completed: true })
    assert.equal(h.state.ttsCalls, 0)
    assert.ok(!h.state.messages.includes('자막 변경 내용을 저장했습니다.'))
    h.confirm(0)
    assert.equal(await pending, true)
    assert.equal(h.state.messages.at(-1), '자막 변경 내용을 저장했습니다.')
    assert.equal(h.state.ttsCalls, 0)
})
