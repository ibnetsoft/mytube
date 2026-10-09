const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const source = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
const ast = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
function findAll(root, predicate) {
    const result = []
    function visit(node) {
        if (predicate(node)) result.push(node)
        ts.forEachChild(node, visit)
    }
    visit(root)
    return result
}
function variable(name, root = ast) {
    const node = findAll(root, item => ts.isVariableDeclaration(item) && item.name.getText(ast) === name)[0]
    assert(node?.initializer, `Missing page function ${name}`)
    return node.initializer
}
function evaluate(node, dependencies = {}) {
    const code = ts.transpileModule(`return (${node.getText(ast)});`, {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
    }).outputText
    return new Function(...Object.keys(dependencies), code)(...Object.values(dependencies))
}
function effect(name, marker) {
    const call = findAll(ast, node => ts.isCallExpression(node) && node.expression.getText(ast) === name
        && node.arguments[0]?.getText(ast).includes(marker))[0]
    assert(call, `Missing ${name}: ${marker}`)
    return call.arguments[0]
}
function onClick(marker) {
    const attribute = findAll(ast, node => ts.isJsxAttribute(node) && node.name.getText(ast) === 'onClick'
        && node.initializer?.getText(ast).includes(marker))[0]
    assert(attribute?.initializer?.expression, `Missing click handler: ${marker}`)
    return attribute.initializer.expression
}

const subtitles = [
    { scene_number: 99, text: 'Previous scene', start_num: 793.3, end_num: 795 },
    { scene_number: 100, text: 'Selected scene', start_num: 793.8, end_num: 796 },
    { scene_number: 100, text: 'Second line', start_num: 796, end_num: 799 },
]

function selectionHarness() {
    const state = { index: 0, time: 793.3, playing: true, transition: { imageUrl: '/old.png' }, stops: 0, blocks: [] }
    const context = {
        localSubtitles: subtitles,
        stopVrewPlayback: () => { state.stops++; state.playing = false },
        setPreviewTransition: value => { state.transition = value },
        setSelectedSubIndex: value => { state.index = value },
        setPlaybackTime: value => { state.time = value },
        setOpenVoicePickerKey() {},
    }
    const selectSubtitlePreview = evaluate(variable('selectSubtitlePreview'), context)
    return { state, context: { ...context, selectSubtitlePreview }, selectSubtitlePreview }
}

test('scene selection wins over overlapping timestamps and cancels previous playback', () => {
    const { state, context, selectSubtitlePreview } = selectionHarness()
    selectSubtitlePreview(1)
    assert.equal(state.index, 1)
    assert.equal(state.time, 793.8)
    assert.equal(state.playing, false)
    assert.equal(state.stops, 1)
    assert.equal(state.transition, null)

    const synchronize = evaluate(effect('useEffect', 'const activeIdx = localSubtitles.findIndex'), {
        ...context, currentNav: 'subtitle_vrew', selectedSubIndex: state.index, playbackTime: state.time,
    })
    synchronize()
    assert.equal(state.index, 1, 'The previous subtitle overlaps 793.8s but must not override an explicit scene selection')
    assert.deepEqual(subtitles.map(row => row.start_num), [793.3, 793.8, 796], 'Previewing cannot modify saved timing')

    selectSubtitlePreview(2)
    selectSubtitlePreview(0)
    selectSubtitlePreview(1)
    assert.equal(state.index, 1, 'The latest of rapid selections owns the preview')
    assert.equal(state.time, 793.8)
})

test('scene card, subtitle block and legacy line controls use the same preview selection', () => {
    const { state, context } = selectionHarness()
    evaluate(onClick('selectSubtitlePreview(group.firstIndex)'), { ...context, group: { firstIndex: 1 } })()
    assert.equal(state.index, 1)

    const anchor = { current: 1 }
    const selectBlock = evaluate(variable('selectSubtitleBlock'), {
        ...context, subtitleBlockSelectionAnchorRef: anchor,
        setSelectedSubtitleBlockIndexes: values => { state.blocks = values }, setMessage() {},
    })
    selectBlock(2, true)
    assert.deepEqual(state.blocks, [1, 2], 'Range selection within a scene remains available')
    assert.equal(state.index, 2)
    assert.equal(state.time, 796)

    let stopped = false
    evaluate(onClick('selectSubtitlePreview(item.subtitleIndex)'), { ...context, item: { subtitleIndex: 0 } })({
        stopPropagation: () => { stopped = true },
    })
    assert(stopped)
    assert.equal(state.index, 0)
    assert.equal(state.stops, 3)
})

test('stopping playback removes pending audio callbacks as well as its timer', () => {
    const state = { paused: 0, loaded: 0, gainDisposed: 0, bgmStopped: 0, playing: true }
    const callback = () => { throw new Error('A stopped audio callback must not run') }
    const audio = {
        onloadedmetadata: callback, onended: callback, onerror: callback,
        pause: () => { state.paused++ }, removeAttribute() {},
        load: () => {
            state.loaded++
            assert.equal(audio.onloadedmetadata, null)
            assert.equal(audio.onended, null)
            assert.equal(audio.onerror, null)
        },
    }
    const vrewPlaybackCancelRef = { current: 4 }
    const vrewAudioRef = { current: audio }
    const vrewProgressTimerRef = { current: 27 }
    const cleared = []
    evaluate(variable('stopVrewPlayback'), {
        speechGainCleanupRef: { current: () => { state.gainDisposed++ } },
        setIsNarrationPlaying() {}, vrewPlaybackCancelRef, vrewProgressTimerRef,
        clearInterval: id => cleared.push(id), vrewAudioRef,
        stopPreviewBgm: () => { state.bgmStopped++ }, vrewPreviewVideoRef: { current: { pause() {} } },
        setIsPlayingPreview: value => { state.playing = value }, setVrewActiveTokenIndex() {},
    })()
    assert.equal(vrewPlaybackCancelRef.current, 5)
    assert.deepEqual(cleared, [27])
    assert.equal(vrewProgressTimerRef.current, null)
    assert.equal(vrewAudioRef.current, null)
    assert.equal(state.playing, false)
    assert.equal(state.paused, 1)
    assert.equal(state.loaded, 1)
    assert.equal(state.gainDisposed, 1)
    assert.equal(state.bgmStopped, 1)
})

test('queued narration callbacks cannot restore a canceled preview selection', () => {
    const play = variable('playVrewSegmentsFrom')
    const callbacks = findAll(play, node => ts.isVariableDeclaration(node) && node.name.getText(ast) === 'syncPlaybackProgress')
        .map(node => node.initializer)
    const metadata = findAll(play, node => ts.isBinaryExpression(node) && node.left.getText(ast) === 'audio.onloadedmetadata'
        && ts.isArrowFunction(node.right))
        .map(node => node.right)
    assert.equal(callbacks.length, 2, 'Both final narration and individual segments have playback clocks')
    assert.equal(metadata.length, 1)
    let writes = 0
    const noWrite = () => { writes++; throw new Error('Canceled callback wrote preview state') }
    const context = {
        cancelToken: 6, vrewPlaybackCancelRef: { current: 7 },
        audio: { currentTime: 793.3, duration: 827.1, pause() {} },
        setPlaybackTime: noWrite, setSelectedSubIndex: noWrite, setVrewActiveTokenIndex: noWrite,
        speechGain: { set: noWrite }, cleanup() {}, resolve() {}, reject: noWrite,
        startTime: 793.3, syncPlaybackProgress: noWrite, setInterval: noWrite,
    }
    for (const callback of [...callbacks, ...metadata]) evaluate(callback, context)()
    assert.equal(writes, 0)
})

test('a failed request from canceled playback cannot stop the next playback session', async () => {
    let rejectRequest
    let stops = 0
    const vrewPlaybackCancelRef = { current: 10 }
    const handleToggle = evaluate(variable('handleToggleVrewPlayback'), {
        isPlayingPreview: false, selectedSubIndex: 1, vrewPlaybackCancelRef,
        playVrewSegmentsFrom: () => {
            vrewPlaybackCancelRef.current++
            return new Promise((resolve, reject) => { rejectRequest = reject })
        },
        stopVrewPlayback: () => { stops++ },
    })
    handleToggle()
    vrewPlaybackCancelRef.current += 2 // Cancel the old selection, then start another.
    rejectRequest(new Error('The previous audio request failed late'))
    await Promise.resolve()
    assert.equal(stops, 0)
})

test('timeline scrubbing updates a paused preview without relying on the playback clock effect', () => {
    const { state, context } = selectionHarness()
    evaluate(onClick('const targetTime ='), { ...context, totalDuration: 1000 })({
        currentTarget: { getBoundingClientRect: () => ({ left: 0, width: 1000 }) }, clientX: 797,
    })
    assert.equal(state.index, 2)
    assert.equal(state.time, 797)
    assert.equal(state.playing, false)
    assert.equal(state.transition, null)
})

test('pause notifications from canceled audio cannot stop the next narration or its background music', () => {
    const play = variable('playVrewSegmentsFrom')
    const bindings = findAll(play, node => ts.isCallExpression(node) && node.expression.getText(ast) === 'bindNarrationPlayback')
    assert.equal(bindings.length, 2)
    let stops = 0
    for (const binding of bindings) {
        evaluate(binding.arguments[2], {
            cancelToken: 2, vrewPlaybackCancelRef: { current: 3 },
            setIsNarrationPlaying: () => { stops++ }, stopPreviewBgm: () => { stops++ },
        })()
    }
    assert.equal(stops, 0)
})

function transitionHarness(options = {}) {
    const state = { transition: { imageUrl: '/stale.png', exiting: false } }
    let nextId = 1
    let now = 0
    const timers = new Map(), frames = new Map(), listeners = new Map()
    const video = {
        readyState: 0,
        addEventListener: (name, callback) => listeners.set(name, callback),
        removeEventListener: (name, callback) => { if (listeners.get(name) === callback) listeners.delete(name) },
    }
    const images = []
    class FakeImage {
        constructor() { this.onload = null; this.onerror = null; images.push(this) }
    }
    const window = {
        Image: FakeImage,
        setTimeout: (callback, delay) => { const id = nextId++; timers.set(id, { callback, due: now + delay }); return id },
        clearTimeout: id => timers.delete(id),
        requestAnimationFrame: callback => { const id = nextId++; frames.set(id, callback); return id },
        cancelAnimationFrame: id => frames.delete(id),
    }
    const context = {
        previewTransitionVisualRef: { current: { sceneNumber: 99, imageUrl: '/previous.png', videoUrl: '' } },
        currentNav: 'subtitle_vrew', isPlayingPreview: true, currentPreviewSceneNumber: 100,
        currentSubImageUrl: '/scene100.png', currentSubVideoUrl: '/scene100.mp4',
        selectedProject: { scenes: [{ scene_number: 100, metadata: { transition_effect: 'fade' } }] },
        setPreviewTransition: update => { state.transition = typeof update === 'function' ? update(state.transition) : update },
        vrewPreviewVideoRef: { current: video }, window, ...options,
    }
    const run = () => evaluate(effect('useLayoutEffect', 'const previousVisual = previewTransitionVisualRef.current'), context)()
    const advance = duration => {
        now += duration
        for (const [id, timer] of [...timers]) if (timer.due <= now) { timers.delete(id); timer.callback() }
        for (const [id, callback] of [...frames]) { frames.delete(id); callback() }
    }
    return { state, context, listeners, timers, images, run, advance }
}

test('paused selections and same-scene URL replacements clear stale transition covers immediately', () => {
    const paused = transitionHarness({ isPlayingPreview: false })
    paused.run()
    assert.equal(paused.state.transition, null)
    assert.equal(paused.listeners.size, 0, 'A paused image poster must not wait for video decoding')
    assert.equal(paused.timers.size, 0)

    const refreshed = transitionHarness({
        previewTransitionVisualRef: { current: { sceneNumber: 100, imageUrl: '/expired.png', videoUrl: '/expired.mp4' } },
    })
    refreshed.run()
    assert.equal(refreshed.state.transition, null, 'Refreshing signed media URLs cannot strand the previous scene above the preview')
    assert.equal(refreshed.context.previewTransitionVisualRef.current.imageUrl, '/scene100.png')
})

test('unresponsive video loading cannot leave a transition cover indefinitely', () => {
    const harness = transitionHarness()
    const cleanup = harness.run()
    assert.equal(harness.state.transition.imageUrl, '/previous.png')
    assert(harness.timers.size > 0, 'A media-load deadline must be scheduled')
    harness.advance(1500)
    harness.advance(600)
    assert.equal(harness.state.transition, null, 'The incoming scene is revealed even when video emits no loadeddata or error')
    cleanup()
    assert.equal(harness.listeners.size, 0)
    assert.equal(harness.timers.size, 0)
})

test('late transition callbacks from a previous selection cannot cover the newest scene', () => {
    const harness = transitionHarness()
    const cleanup = harness.run()
    const staleLoaded = harness.listeners.get('loadeddata')
    assert(staleLoaded)
    cleanup()
    const newest = { imageUrl: '/newest.png', exiting: false }
    harness.state.transition = newest
    staleLoaded()
    harness.advance(5000)
    assert.equal(harness.state.transition, newest)
    assert.equal(harness.listeners.size, 0)
})

test('profile hydration keeps the in-flight project generation valid, but auth changes do not', () => {
    const session = (token, user, impersonateEmail = '') => evaluate(variable('mediaSession'), {
        token, user, isImpersonating: Boolean(impersonateEmail), impersonateEmail,
    })
    const initial = session('session-a', null)
    assert.equal(session('session-a', { id: 'user-a', email: 'a@example.test' }), initial)
    assert.equal(session('session-a', { id: 'user-a', full_name: 'Updated profile' }), initial)
    assert.notEqual(session('session-b', { id: 'user-b' }), initial)
    assert.notEqual(session('', null), initial)
    assert.notEqual(session('session-a', null, 'other@example.test'), initial)
})
