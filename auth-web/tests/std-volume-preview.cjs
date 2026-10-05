const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')
const page = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
function load(name) {
    const file = path.resolve(__dirname, '../lib', name + '.ts')
    const exports = {}
    new Function('exports', 'require', ts.transpile(fs.readFileSync(file, 'utf8'), { module: 1, target: 7 }))(
        exports, dependency => load(dependency.replace('./', '')))
    return exports
}
const preview = load('stdPreviewAudio')
const { subtitleGain } = load('stdSpeechGain')
function extract(start, end, result, context) {
    const from = page.indexOf(start), to = page.indexOf(end, from)
    assert(from >= 0 && to > from)
    const code = ts.transpile(`${page.slice(from, to)}; return ${result}`, { target: 7 })
    return new Function(...Object.keys(context), code)(...Object.values(context))
}
const row = (text, speaker = 'お鈴') => ({ text, voice_id: 'saved-voice', dialogue_speaker: speaker, volume: 100 })

test('volume edits save metadata, preserve recordings and compose with the latest draft', async () => {
    const original = [row('one'), row('two', '大五郎'), row('three')]
    const speechSubtitlesRef = { current: original }
    const saves = []
    const apply = extract('    const applySubtitleVolume =', '    const renderAiDialogue =', 'applySubtitleVolume', {
        localSubtitles: original, speechSubtitlesRef,
        subtitleSpeakers: original.map(s => ({ name: s.dialogue_speaker })),
        persistVrewVoiceSubtitles: async (subtitles, options) => {
            assert.equal(options?.strict, undefined, 'Autosave failure is handled by the save state, not an unhandled picker rejection')
            speechSubtitlesRef.current = subtitles
            saves.push(subtitles)
            return false // A failed autosave must not throw out of the volume callback.
        },
    })
    await apply(0, 65, true)
    assert.deepEqual(saves[0].map(s => s.volume), [65, 100, 65])
    assert.equal(saves[0][1], original[1])
    assert.equal(subtitleGain(saves[0][0]), 0.65)
    speechSubtitlesRef.current[1] = { ...speechSubtitlesRef.current[1], text: 'latest edit' }
    await apply(2, 0)
    assert.equal(saves[1][1].text, 'latest edit')
    assert.deepEqual(saves[1].map(s => s.volume), [65, 100, 0])
    assert.equal(subtitleGain(saves[1][2]), 0)
    assert.deepEqual(saves[0][0], { ...original[0], volume: 65, volume_ratio: 0.65 })
})

function audioHarness({ missing = false, respond } = {}) {
    const requests = [], state = { messages: [], playing: false, highlights: [], errors: [] }
    const subtitles = [{ ...row('existing recording'), start_num: 0, end_num: 1 }]
    const project = { project: { id: 'project' }, assets: [{ id: 'full', asset_type: 'audio', status: 'uploaded', metadata: {
        subtitle_timeline: [{ text: 'a different saved timeline', voice_id: 'saved-voice', start: 0, end: 1 }],
    } }] }
    const context = {
        ...preview, selectedProject: project, localSubtitles: subtitles, selectedVoice: 'saved-voice',
        legacyStorageErrorPattern: /invalid_grant|drive_credentials_not_configured/,
        ttsSpeed: '1', elStability: '0.7', elStyle: '0.45', currentLocale: 'ko',
        vrewAudioCacheRef: { current: {} }, vrewAudioPromiseRef: { current: new Map() },
        vrewFinalNarrationAudioRef: { current: null }, vrewPlaybackCancelRef: { current: 0 },
        speechContextRef: { current: { resume: async () => {} } },
        setVrewSegmentStatus() {}, isVoiceStudioVoice: () => false,
        setIsPlayingPreview: value => { state.playing = value }, setIsNarrationPlaying() {},
        setPreviewAudioError: value => state.errors.push(value),
        setHighlightSaveTts: value => state.highlights.push(value),
        setSelectedSubIndex() {}, setPlaybackTime() {}, stopPreviewBgm() {},
        setMessage: value => state.messages.push(value), authedJsonHeaders: {},
        fetch: async (url, options) => {
            const body = JSON.parse(options.body)
            requests.push(body)
            if (respond) return respond(body)
            return missing ? Response.json({ success: false, code: 'audio_not_cached', error: '저장된 구간 음성이 없습니다.' }, { status: 404 })
                : Response.json({ success: true, cached: true, audio_url: 'blob:stored-clip' })
        },
        safeParseJson: response => response.json(), isSameOriginApiAudioUrl: () => false,
    }
    context.vrewSegmentCacheKey = extract('    const vrewSegmentCacheKey =', '    const vrewTextTokens =', 'vrewSegmentCacheKey', context)
    context.getSavedNarrationAudioUrl = extract('    const getSavedNarrationAudioUrl =', '    const hasStoredSegment =', 'getSavedNarrationAudioUrl', context)
    context.getOrCreateVrewSegmentAudioUrl = extract('    const getOrCreateVrewSegmentAudioUrl =', '    const prefetchVrewSegment =', 'getOrCreateVrewSegmentAudioUrl', context)
    context.playVrewSegmentsFrom = extract('    const playVrewSegmentsFrom =', '    const handleToggleVrewPlayback =', 'playVrewSegmentsFrom', context)
    return { context, requests, state, subtitles }
}

test('preview reads stored audio and reuses it across mute and volume changes', async () => {
    const h = audioHarness()
    const get = h.context.getOrCreateVrewSegmentAudioUrl
    assert.equal(await get(h.subtitles[0], 0), 'blob:stored-clip')
    assert.equal(h.requests[0].cache_only, true)
    assert.equal(h.requests.length, 1)
    for (const volume of [65, 0, 200]) {
        assert.equal(await get({ ...h.subtitles[0], volume, volume_ratio: volume / 100 }, 0), 'blob:stored-clip')
    }
    assert.equal(h.requests.length, 1, 'Volume never changes the audio identity or requests synthesis')
})

test('mismatched full narration falls back to cache-only preview and prompts for explicit TTS on a missing clip', async () => {
    const h = audioHarness({ missing: true })
    await h.context.playVrewSegmentsFrom(0)
    assert.equal(h.requests.length, 1)
    assert.equal(h.requests[0].cache_only, true)
    assert.equal(h.state.playing, false)
    assert.equal(h.state.highlights.at(-1), true)
    assert.match(h.state.messages.at(-1), /저장\+TTS/)
    assert(h.state.errors.every(message => !message), 'Missing audio is guidance, not a provider error')
})

test('the explicit timing correction action can still prepare audio when requested', async () => {
    const h = audioHarness()
    await h.context.getOrCreateVrewSegmentAudioUrl(h.subtitles[0], 0, undefined, false)
    assert.equal(h.requests[0].cache_only, false)
})

test('an in-flight read-only miss never blocks an explicit generation request', async () => {
    let resolveLookup
    const h = audioHarness({ respond: body => body.cache_only
        ? new Promise(resolve => { resolveLookup = resolve })
        : Response.json({ success: true, audio_url: 'blob:generated-clip' }) })
    const get = h.context.getOrCreateVrewSegmentAudioUrl
    const lookup = get(h.subtitles[0], 0)
    const failure = assert.rejects(lookup, error => error.code === 'audio_not_cached')
    const generation = get(h.subtitles[0], 0, undefined, false)
    resolveLookup(Response.json({ success: false, code: 'audio_not_cached' }, { status: 404 }))
    await failure
    assert.equal(await generation, 'blob:generated-clip')
    assert.deepEqual(h.requests.map(body => body.cache_only), [true, false])
})

test('missing recording guidance follows Korean, Thai and Vietnamese UI modes', () => {
    assert.equal(preview.isSavedAudioRequiredError({ code: 'audio_not_cached', status: 404 }), true)
    assert.equal(preview.isSavedAudioRequiredError({ status: 401, message: 'ElevenLabs payment_issue' }), false)
    assert.match(preview.savedAudioRequiredMessage('th-TH'), /[ก-๛]/)
    assert.match(preview.savedAudioRequiredMessage('vi'), /âm lượng/)
    assert.match(preview.savedAudioRequiredMessage('ko'), /볼륨/)
})
