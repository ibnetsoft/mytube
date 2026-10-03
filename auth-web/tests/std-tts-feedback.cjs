const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const page = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) }
function load(file) {
    const exports = {}
    new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.resolve(__dirname, file), 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText)(exports, id => {
        if (id === 'react/jsx-runtime') return jsx
        if (id === 'lucide-react') return { AlertCircle: 'alert-icon', CheckCircle2: 'success-icon', RefreshCw: 'spinner', X: 'close-icon' }
        throw Error(`Unexpected dependency: ${id}`)
    })
    return exports
}
const { isCurrentMediaScope, assetBelongsToProject } = load('../lib/stdMediaScope.ts')
const { default: StdTtsNotice, ttsNoticeCopy } = load('../components/StdTtsNotice.tsx')
function extract(start, end, result, context) {
    const from = page.indexOf(start), to = page.indexOf(end, from)
    assert.ok(from >= 0 && to > from, `Missing page function: ${start}`)
    const compiled = ts.transpileModule(`${page.slice(from, to)}\nreturn ${result}`, {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    return new Function(...Object.keys(context), compiled)(...Object.values(context))
}
function project(id) {
    return { project: { id, title: `Title ${id}`, project_payload: { script: 'Saved script.' }, progress_payload: {} }, assets: [{ id: `${id}-image`, asset_type: 'image', project_id: id }] }
}
const asset = { id: 'saved-audio', project_id: 'project-a', asset_type: 'audio', drive_file_id: 'gcs-audio' }
const successfulPayload = () => ({ success: true, asset, audio_url: '/saved-audio', segment_reuse: { reused: 4, generated: 2 } })
function deferred() {
    let resolve, reject
    const promise = new Promise((yes, no) => { resolve = yes; reject = no })
    return { promise, resolve, reject }
}
function harness(options = {}) {
    const selectedProject = project('project-a')
    const state = { project: selectedProject, audio: 'initial-audio', notices: [], spinning: [], alerts: [], messages: [], remembered: [], requests: [], revoked: [], fallbackCalls: 0, saves: 0 }
    const mediaScopeRef = { current: { session: 'session-a', projectId: 'project-a', generation: 1 } }
    const context = {
        selectedProject, mediaScopeRef, isCurrentMediaScope, assetBelongsToProject, currentLocale: 'ko', ttsNoticeCopy,
        currentNav: options.nav || 'subtitle_vrew',
        getProjectSyncedTitle: p => p?.project?.title || '',
        setTtsNotice: notice => state.notices.push(notice), setGeneratingTts: value => state.spinning.push(value),
        setMessage: value => state.messages.push(value), setAudioResultUrl: value => { state.audio = value },
        setSelectedProject: next => { state.project = typeof next === 'function' ? next(state.project) : next },
        rememberProjectState: value => state.remembered.push(value), alert: value => state.alerts.push(value),
        ensureScriptSyncedBeforeAction: async () => options.sync !== false,
        allVoices: [{ id: 'voice-a', name: 'Voice A' }], STD_DEFAULT_VOICE: { id: 'voice-a', name: 'Voice A' },
        selectedVoice: options.voice || 'voice-a',
        subtitleVoiceSegments: () => options.segments ?? [{ text: 'Saved script.', voice_id: 'voice-a' }],
        isVoiceStudioVoice: voice => voice.startsWith('gemini:'), customScriptText: '',
        ttsSpeed: '1', elStability: '0.7', elStyle: '0.45', multiVoice: false, detectedCharacters: [], characterVoices: {},
        authedJsonHeaders: { Authorization: 'Bearer fixture' }, safeParseJson: async response => response.payload,
        formatTtsErrorMessage: value => value, shouldUseBrowserElevenLabsFallback: () => Boolean(options.fallback),
        generateElevenLabsAudioInBrowser: async () => { state.fallbackCalls++; return new Blob(['fixture audio']) },
        URL: { createObjectURL: () => 'blob:fixture-audio', revokeObjectURL: url => state.revoked.push(url) },
        console: { warn() {} },
        fetch: async (url, init) => {
            state.requests.push({ url, init })
            if (url.endsWith('/tts/generate')) return { ok: options.status !== 500, status: options.status || 200, payload: options.payload ?? successfulPayload() }
            if (url === '/api/std/tts-proxy') return { ok: true, arrayBuffer: async () => new Uint8Array(300).buffer }
            if (url === '/saved-audio') return { ok: true, blob: async () => new Blob([new Uint8Array(300)]) }
            throw Error(`Unexpected fetch: ${url}`)
        },
        generateNarrationInBatches: async (body, send, progress) => {
            if (options.gate) await options.gate.promise
            if (options.batchError) throw Error(options.batchError)
            progress(1, 2)
            progress(2, 2)
            const reply = await send(body)
            return reply
        },
        hasDistinctDialogueVoiceAssignment: () => options.assignment !== false,
        setHighlightSaveTts() {},
        handleSaveSubtitles: async () => {
            state.saves++
            if (options.saveGate) await options.saveGate.promise
            if (options.saveError) throw Error(options.saveError)
        },
    }
    const generateTts = extract('    const generateTts =', '    const setSelectedSubtitleBlocksVoice =', 'generateTts', context)
    const handleFinalizeSubtitlesAndTts = extract('    const handleFinalizeSubtitlesAndTts =', '    // 대본 속 인물', 'handleFinalizeSubtitlesAndTts', { ...context, generateTts })
    return { state, mediaScopeRef, generateTts, handleFinalizeSubtitlesAndTts }
}
const terminal = h => h.state.notices.filter(notice => notice.phase !== 'running')

test('Save + TTS shows completion once after saved audio, with reuse counts, and stops spinning', async () => {
    const h = harness()
    await h.handleFinalizeSubtitlesAndTts()
    assert.equal(h.state.saves, 1)
    assert.deepEqual(terminal(h).map(notice => notice.phase), ['success'])
    assert.equal(terminal(h)[0].projectTitle, 'Title project-a')
    assert.match(terminal(h)[0].detail, /기존 4개 재사용 · 새로 2개 생성/)
    assert.equal(h.state.project.assets[0], asset)
    assert.equal(h.state.audio, 'blob:fixture-audio')
    assert.equal(h.state.spinning.at(-1), false)
    assert.equal(h.state.alerts.length, 0)
})

test('subtitle persistence failure never invokes TTS or reports completion', async () => {
    const h = harness({ saveError: 'Subtitle save unavailable' })
    await h.handleFinalizeSubtitlesAndTts()
    assert.deepEqual(terminal(h).map(notice => notice.phase), ['error'])
    assert.equal(h.state.requests.length, 0)
    assert.equal(h.state.audio, 'initial-audio')
    assert.equal(h.state.spinning.at(-1), false)
})

test('preparation and final assembly errors never produce success notices', async () => {
    for (const options of [
        { batchError: 'TTS generation failed (prepare_saved_segments): provider unavailable' },
        { status: 500, payload: { success: false, stage: 'assemble_narration_segments', error: 'Assembly unavailable' } },
    ]) {
        const h = harness(options)
        await h.handleFinalizeSubtitlesAndTts()
        assert.deepEqual(terminal(h).map(notice => notice.phase), ['error'])
        assert.equal(h.state.remembered.length, 0)
        assert.equal(h.state.spinning.at(-1), false)
        assert.equal(h.state.alerts.length, 1)
    }
})

test('missing or foreign persisted assets show a warning instead of save success', async () => {
    for (const saved of [null, { ...asset, project_id: 'project-b' }]) {
        const h = harness({ payload: { ...successfulPayload(), asset: saved } })
        await h.generateTts(true)
        assert.deepEqual(terminal(h).map(notice => notice.phase), ['warning'])
        assert.equal(h.state.remembered.length, 0)
        assert.equal(h.state.project.assets.length, 1)
        assert.equal(h.state.spinning.at(-1), false)
    }
})

test('browser fallback audio and failed Google persistence never claim server save success', async () => {
    for (const options of [
        { segments: [], nav: 'tts', fallback: true, status: 500, payload: { success: false, error: 'Server persistence unavailable' } },
        { segments: [], nav: 'tts', voice: 'google_ko', status: 500, payload: { error: 'Server persistence unavailable' } },
    ]) {
        const h = harness(options)
        await h.generateTts(true)
        assert.deepEqual(terminal(h).map(notice => notice.phase), ['warning'])
        assert.equal(h.state.audio, 'blob:fixture-audio')
        assert.equal(h.state.remembered.length, 0)
        assert.equal(h.state.spinning.at(-1), false)
        assert.equal(h.state.fallbackCalls, options.fallback ? 1 : 0)
    }
})

test('an in-flight operation can finish under an unchanged page scope and reports its project', async () => {
    const gate = deferred(), h = harness({ gate })
    const running = h.generateTts(true)
    assert.equal(h.state.spinning.at(-1), true)
    assert.equal(terminal(h).length, 0)
    // Sidebar tab changes leave this shared page's media scope and async closure intact.
    gate.resolve()
    await running
    assert.deepEqual(terminal(h).map(notice => notice.phase), ['success'])
    assert.equal(terminal(h)[0].projectId, 'project-a')
    assert.equal(h.state.audio, 'blob:fixture-audio')
})

test('project switch and A-to-B-to-A generation changes preserve the current project audio/state', async () => {
    for (const nextProjectId of ['project-b', 'project-a']) {
        const gate = deferred(), h = harness({ gate })
        const running = h.generateTts(true)
        h.mediaScopeRef.current = { ...h.mediaScopeRef.current, projectId: nextProjectId, generation: 2 }
        h.state.project = project(nextProjectId)
        const currentProject = h.state.project
        h.state.audio = 'new-project-audio'
        gate.resolve()
        await running
        assert.equal(h.state.project, currentProject)
        assert.equal(h.state.audio, 'new-project-audio')
        assert.deepEqual(h.state.remembered, [])
        assert.deepEqual(h.state.revoked, ['blob:fixture-audio'])
        assert.deepEqual(terminal(h).map(notice => notice.phase), ['success'])
        assert.equal(terminal(h)[0].projectId, 'project-a')
        assert.match(h.state.requests[0].url, /\/project-a\/tts\/generate$/)
        assert.equal(h.state.spinning.at(-1), false)
    }
})

test('a changed login session receives neither old audio nor completion notices', async () => {
    const gate = deferred(), h = harness({ gate })
    const running = h.generateTts(true)
    h.mediaScopeRef.current = { ...h.mediaScopeRef.current, session: 'session-b', generation: 2 }
    gate.resolve()
    await running
    assert.equal(terminal(h).length, 0)
    assert.equal(h.state.audio, 'initial-audio')
    assert.equal(h.state.remembered.length, 0)
    assert.equal(h.state.spinning.at(-1), false)
})

test('project changes during the initial subtitle save keep the original TTS scope and project', async () => {
    for (const nextProjectId of ['project-b', 'project-a']) {
        const saveGate = deferred(), h = harness({ saveGate })
        const running = h.handleFinalizeSubtitlesAndTts()
        assert.equal(h.state.saves, 1)
        assert.equal(h.state.requests.length, 0)
        h.mediaScopeRef.current = { ...h.mediaScopeRef.current, projectId: nextProjectId, generation: 2 }
        h.state.project = project(nextProjectId)
        const currentProject = h.state.project
        h.state.audio = 'new-project-audio'
        saveGate.resolve()
        await running
        assert.equal(h.state.project, currentProject)
        assert.equal(h.state.audio, 'new-project-audio')
        assert.deepEqual(h.state.remembered, [])
        assert.deepEqual(h.state.revoked, ['blob:fixture-audio'])
        assert.match(h.state.requests[0].url, /\/project-a\/tts\/generate$/)
        assert.deepEqual(terminal(h).map(notice => notice.phase), ['success'])
        assert.equal(terminal(h)[0].projectId, 'project-a')
        assert.equal(h.state.spinning.at(-1), false)
    }
})

test('refresh/close protection stays active during TTS after subtitles are saved, then cleans up', () => {
    const start = page.lastIndexOf('    useEffect(() => {', page.indexOf('const protectUnsavedEdits'))
    const end = page.indexOf('    const [subPresetList', start)
    const compiled = ts.transpileModule(page.slice(start, end), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
    for (const [generatingTts, subtitleSaveState, protectedState] of [[true, 'saved', true], [false, 'saved', false], [false, 'dirty', true], [false, 'saving', true], [false, 'error', true]]) {
        const listeners = new Map()
        let cleanup
        new Function('useEffect', 'window', 'generatingTts', 'subtitleSaveState', compiled)(effect => { cleanup = effect() }, {
            addEventListener: (type, callback) => listeners.set(type, callback),
            removeEventListener: (type, callback) => { assert.equal(listeners.get(type), callback); listeners.delete(type) },
        }, generatingTts, subtitleSaveState)
        assert.equal(listeners.has('beforeunload'), protectedState)
        if (protectedState) {
            let prevented = false
            const event = { preventDefault: () => { prevented = true } }
            listeners.get('beforeunload')(event)
            assert.equal(prevented, true)
            assert.equal(event.returnValue, '')
            cleanup()
            assert.equal(listeners.size, 0)
        }
    }
})

const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value)
    ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)]
test('notice is localized, accessible, persistent until dismissal, and clear about keeping the tab open', () => {
    assert.equal(StdTtsNotice({ notice: null, locale: 'ko', onDismiss() {} }), null)
    for (const locale of ['ko', 'th', 'en', 'vi']) {
        for (const phase of ['running', 'success', 'warning', 'error']) {
            let dismissed = 0
            const copy = ttsNoticeCopy(locale)
            const tree = nodes(StdTtsNotice({ notice: { projectId: 'project-a', projectTitle: 'Project A', phase, detail: 'Operation detail' }, locale, onDismiss: () => { dismissed++ } }))
            const region = tree.find(node => node.type === 'section')
            assert.equal(region.props['aria-label'], copy[phase])
            assert.ok(tree.some(node => node.props.role === (phase === 'error' ? 'alert' : 'status')))
            const buttons = tree.filter(node => node.type === 'button')
            if (phase === 'running') {
                assert.equal(buttons.length, 0)
                assert.ok(tree.some(node => node.props.children === copy.navigation))
            } else {
                assert.ok(buttons.length > 0)
                buttons[0].props.onClick()
                assert.equal(dismissed, 1)
            }
        }
    }
})
