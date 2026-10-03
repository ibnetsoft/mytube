const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
function extract(start, end, name, context = {}) {
    const from = page.indexOf(start)
    const to = page.indexOf(end, from)
    assert(from >= 0 && to > from, `Missing page function ${name}`)
    const source = page.slice(from, to) + `\nreturn ${name}`
    const compiled = ts.transpileModule(source, {
        compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
    }).outputText
    return new Function(...Object.keys(context), compiled)(...Object.values(context))
}

function loadLibrary(file) {
    const filename = path.resolve(__dirname, '../lib', file)
    const exports = {}
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    new Function('exports', 'require', compiled)(exports, dependency =>
        loadLibrary(path.relative(path.resolve(__dirname, '../lib'), path.resolve(path.dirname(filename), dependency + '.ts'))))
    return exports
}
const { createSubtitleSaveQueue } = loadLibrary('stdSubtitlePersistence.ts')
const { restoreSavedSubtitleSnapshot } = loadLibrary('stdSubtitleSnapshot.ts')

const scanQuotes = extract('const DIALOGUE_QUOTE_OPEN_TO_CLOSE:', 'export default function StdPortalPage', 'scanDialogueQuoteState')
const fixture = () => [
    { scene_number: 1, text: '첫 번째 설명입니다.' },
    { scene_number: 1, text: '수동으로 지정한 대사입니다.', dialogue_override: true },
    { scene_number: 1, text: '인물이 확인된 대사입니다.', dialogue_speaker: '덕수', editor_speaker: { name: '덕수', text: '인물이 확인된 대사입니다.', gender: 'male' } },
    { scene_number: 1, text: 'AI가 확인한 대사입니다.', aiDialogue: true },
    { scene_number: 1, text: '「누구냐?」' },
    { scene_number: 2, text: '아직 확인하지 않은 노란 후보입니다.', pending: true },
    { scene_number: 2, text: '「책 제목」이라는 설명입니다.', dialogue_override: false, dialogue_speaker: '이전 화자' },
    { scene_number: 2, text: '두 번째 설명입니다.' },
    { scene_number: 3, text: '세 번째 설명입니다.' },
    { scene_number: 2, text: '설명 다음에 실제 대사가 섞였습니다.', aiDialogue: true, mixed: true },
    { scene_number: 4, text: '「화자 확인 필요」' },
    { scene_number: 4, text: '이 씬은 대사만 있습니다.', dialogue_override: true },
    { scene_number: 4, text: '확인 대기 중입니다.', pending: true },
].map((row, index) => ({
    id: `subtitle-${index}`,
    voice_id: `original-voice-${index}`,
    voice_name: `Original ${index}`,
    voice_direction: `Original direction ${index}`,
    start_num: index * 2,
    end_num: index * 2 + 2,
    audio_asset_id: `recording-${index}`,
    audio_url: `/api/audio/${index}`,
    volume: 85,
    translation_manual: true,
    ...row,
}))

function harness(selectedScenes, rows = fixture()) {
    const aiDialogueParts = new Map(rows.flatMap((row, index) => row.aiDialogue ? [[index, [
        ...(row.mixed ? [{ text: '설명 다음에 ', dialogue: false }] : []),
        { text: row.text, dialogue: true, speaker: '순임' },
    ]]] : []))
    const isSubtitleDialogue = extract('    const isSubtitleDialogue =', '    const pendingDialogueCandidateIndexes', 'isSubtitleDialogue', {
        aiDialogueParts,
        hasDialogueQuoteText: text => scanQuotes(text).isDialogue,
    })
    const isSubtitleNarration = extract('    const isSubtitleNarration =', '    const hasDistinctDialogueVoiceAssignment', 'isSubtitleNarration', {
        isSubtitleDialogue,
        pendingDialogueCandidateIndexes: new Set(rows.flatMap((row, index) => row.pending ? [index] : [])),
    })
    const initialProject = { project: { id: 'project-id', project_payload: { subtitles: rows }, progress_payload: {} } }
    const result = { local: rows, project: initialProject, remembered: [], requests: [], stale: [], savedFlags: [], saveStates: [], stops: 0, messages: [] }
    const setters = {
        setLocalSubtitles: next => { result.local = next },
        setIsSubtitleSaved: value => result.savedFlags.push(value),
        setSubtitleSaveState: value => result.saveStates.push(value),
        setSelectedProject: update => { result.project = update(result.project) },
        rememberProjectState: next => result.remembered.push(next),
        setMessage: value => result.messages.push(value),
    }
    const refs = {
        speechSubtitlesRef: { current: rows },
        subtitleSaveRevisionRef: { current: 0 },
        subtitleTextSaveTimerRef: { current: null },
        subtitleStyleSaveTimerRef: { current: null },
        subtitleActiveProjectRef: { current: 'project-id' },
    }
    const updateSubtitleDraft = extract('    const updateSubtitleDraft =', '    const persistVrewVoiceSubtitles =', 'updateSubtitleDraft', {
        ...setters, ...refs,
    })
    const persistVrewVoiceSubtitles = extract('    const persistVrewVoiceSubtitles =', '    const scheduleSubtitleTextSave =', 'persistVrewVoiceSubtitles', {
        ...setters, ...refs, updateSubtitleDraft, restoreSavedSubtitleSnapshot,
        selectedProject: initialProject,
        currentLocale: 'ko',
        authedJsonHeaders: { Authorization: 'Bearer fixture' },
        saveSubtitleProject: createSubtitleSaveQueue(async (url, options) => {
            const body = JSON.parse(options.body)
            result.requests.push({ url, ...options, body })
            return Response.json({ success: true, project: {
                ...result.project.project,
                project_payload: { ...result.project.project.project_payload, ...body.project_payload },
                progress_payload: { ...result.project.project.progress_payload, ...body.progress_payload },
            } })
        }),
    })
    const setVoice = extract('    const setSubtitleGroupVoice =', '    const sceneEffectSavingRef', 'setSubtitleGroupVoice', {
        selectedVoice: 'gemini:Charon',
        selectedSubtitleSceneNumbers: selectedScenes,
        currentNav: 'subtitle_vrew',
        isPlayingPreview: true,
        stopVrewPlayback: () => { result.stops++ },
        localSubtitles: rows,
        isSubtitleNarration,
        voiceNameById: new Map([['gemini:Aoede', 'Aoede'], ['new-eleven-voice', 'New ElevenLabs voice']]),
        markVrewSegmentStale: (item, index) => result.stale.push({ item, index }),
        persistVrewVoiceSubtitles,
        setMessage: value => result.messages.push(value),
    })
    return { rows, result, setVoice, isSubtitleNarration }
}

function assertScope(h, changedIndexes, voiceId, direction) {
    const { rows, result } = h
    const changed = new Set(changedIndexes)
    assert.deepEqual(result.stale.map(entry => entry.index), changedIndexes)
    assert.equal(result.requests.length, 1)
    assert.equal(result.requests[0].method, 'PATCH')
    assert.equal(result.requests[0].url, '/api/std/projects/project-id')
    const persisted = result.requests[0].body.project_payload.subtitles
    assert.deepEqual(persisted, result.local)
    assert.deepEqual(result.project.project.project_payload.subtitles, result.local)
    assert.deepEqual(result.remembered[0].project.project_payload.subtitles, result.local)
    assert.deepEqual(result.savedFlags, [false, true])
    assert.deepEqual(result.saveStates, ['dirty', 'saving', 'saved'])
    rows.forEach((original, index) => {
        if (changed.has(index)) {
            assert.notEqual(result.local[index], original)
            assert.deepEqual(result.local[index], {
                ...original,
                voice_id: voiceId,
                voice_name: voiceId === 'gemini:Aoede' ? 'Aoede' : 'New ElevenLabs voice',
                ...(direction !== undefined ? { voice_direction: direction } : {}),
            })
        } else {
            assert.deepEqual(result.local[index], original, `Protected row ${index} retains its metadata after snapshot normalization`)
            assert.deepEqual(persisted[index], original, `Protected row ${index} retains saved voice, audio, timing and attribution`)
        }
    })
}

test('selecting all scenes changes narration only and preserves confirmed speakers, AI dialogue, quoted unknown speakers and pending rows', async () => {
    const h = harness([1, 2, 3, 4])
    assert.equal(h.isSubtitleNarration(h.rows[6], 6), true, 'Explicit narration overrides old speaker metadata and quotes')
    await h.setVoice({ scene_number: 1 }, 'gemini:Aoede', 'Calm narration')
    assertScope(h, [0, 6, 7, 8], 'gemini:Aoede', 'Calm narration')
})

test('a partial selection changes narration only in selected scenes and preserves directions when omitted', async () => {
    const h = harness([2])
    await h.setVoice({ scene_number: 2 }, 'new-eleven-voice')
    assertScope(h, [6, 7], 'new-eleven-voice')
})

test('a scene narration picker outside the current selection affects only its own narration', async () => {
    const h = harness([1, 2])
    await h.setVoice({ scene_number: 3 }, 'gemini:Aoede', '')
    assertScope(h, [8], 'gemini:Aoede', '')
})

test('a selection containing only dialogue and pending rows does not save or invalidate audio', async () => {
    const h = harness([4])
    await h.setVoice({ scene_number: 4 }, 'gemini:Aoede', 'Do not apply')
    assert.equal(h.result.local, h.rows)
    assert.deepEqual(h.result.stale, [])
    assert.deepEqual(h.result.requests, [])
    assert.deepEqual(h.result.remembered, [])
    assert.deepEqual(h.result.savedFlags, [])
    assert.equal(h.result.stops, 0)
})

test('assigning a character voice before narration bulk preserves that voice and recording metadata after save and reload', async () => {
    const speakerModule = {}
    new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdSpeakerAssignment.ts'), 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
    }).outputText)(speakerModule)
    const rows = fixture()
    rows[3].editor_speaker = { name: '덕수', gender: 'male', text: rows[3].text }
    const speakers = rows.map(row => speakerModule.subtitleSpeaker(row, undefined, []))
    const assigned = speakerModule.assignSpeakerVoice(rows, 2, 'character-eleven', 'Character actor', true, speakers)
    assert.equal(assigned[2].voice_id, 'character-eleven')
    assert.equal(assigned[3].voice_id, 'character-eleven')

    const h = harness([1, 2, 3, 4], assigned)
    await h.setVoice({ scene_number: 1 }, 'gemini:Aoede', 'Calm narration')
    assertScope(h, [0, 6, 7, 8], 'gemini:Aoede', 'Calm narration')
    const reloadedRows = JSON.parse(JSON.stringify(h.result.requests[0].body.project_payload.subtitles))
    for (const index of [2, 3]) {
        assert.deepEqual(reloadedRows[index], assigned[index])
        assert.equal(reloadedRows[index].audio_asset_id, rows[index].audio_asset_id)
        assert.equal(reloadedRows[index].voice_id, 'character-eleven')
    }

    const reopened = harness([1, 2, 3, 4], reloadedRows)
    await reopened.setVoice({ scene_number: 1 }, 'new-eleven-voice')
    assertScope(reopened, [0, 6, 7, 8], 'new-eleven-voice')
    for (const index of [2, 3]) assert.equal(reopened.result.local[index].voice_id, 'character-eleven')
})
