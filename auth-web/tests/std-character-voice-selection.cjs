const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const test = require('node:test')
const ts = require('typescript')
const load = file => { const box = {}; new Function('exports', 'require', ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: 1, target: 9 } }).outputText)(box, name => load(path.resolve(path.dirname(file), name + '.ts'))); return box }
const lib = path.resolve(__dirname, '../lib')
const { assignSpeakerVoice, subtitleSpeaker } = load(lib + '/stdSpeakerAssignment.ts')
const { mapDialogueAnnotations, splitSubtitleDialogueBlocks } = load(lib + '/stdDialogueAnnotations.ts')
const { subtitleTtsReadiness } = load(lib + '/stdTtsReadiness.ts')
const speaker = (name, gender = 'male') => ({ name, gender, label: name })
const row = (text, voice_id, name) => ({ text, voice_id, scene_number: 64, dialogue_kind: name ? 'dialogue' : 'narration', start_num: 1, end_num: 4, text_ko: '보존할 번역', audio_url: '/existing.mp3', ...(name ? { editor_speaker: { name, gender: 'male', text } } : {}) })
const speakersFor = rows => rows.map(r => r.dialogue_override === false ? null : subtitleSpeaker(r, undefined, []))
const page = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
const extract = (from, to, expression, context) => new Function(...Object.keys(context), ts.transpileModule(page.slice(page.indexOf(from), page.indexOf(to, page.indexOf(from))) + '\nreturn ' + expression, { compilerOptions: { target: 9 } }).outputText)(...Object.values(context))

test('explicit character voice selection creates the missing speaker and survives save/reopen', () => {
    const rows = [row('三千両も取り上げたそうだな。', 'narrator'), row('「開けろ。', 'adam', '仙太郎')]
    const before = structuredClone(rows)
    const changed = assignSpeakerVoice(rows, 0, 'adam', 'Adam', true, speakersFor(rows))
    assert.equal(changed[0].dialogue_override, true)
    assert.equal(changed[0].dialogue_kind, 'dialogue')
    assert.equal(changed[0].dialogue_speaker, '仙太郎')
    assert.equal(changed[1], rows[1], 'A narration row never scopes all-speaker edits to other narration rows')
    for (const key of ['text', 'text_ko', 'start_num', 'end_num', 'audio_url']) assert.equal(changed[0][key], rows[0][key])
    const reopened = splitSubtitleDialogueBlocks(JSON.parse(JSON.stringify(changed)), undefined, true, 100)
    assert.equal(subtitleSpeaker(reopened[0], undefined, []).name, '仙太郎')
    assert.deepEqual(rows, before)
})

test('reselecting an already saved character voice repairs a misclassified row and overrides manual narration', () => {
    const rows = [{ ...row('続きの台詞。', 'adam'), dialogue_override: false }, row('「開けろ。', 'adam', '仙太郎')]
    const changed = assignSpeakerVoice(rows, 0, 'adam', 'Adam', false, speakersFor(rows))
    assert.equal(changed[0].editor_speaker.name, '仙太郎')
    assert.equal(changed[0].dialogue_override, true)
})

test('shared actors expose an unresolved dialogue button instead of guessing a character', () => {
    const rows = [row('続き。', 'narrator'), row('一。', 'adam', '兄'), row('二。', 'adam', '弟')]
    const changed = assignSpeakerVoice(rows, 0, 'adam', 'Adam', false, speakersFor(rows))
    assert.equal(changed[0].dialogue_override, true)
    assert.equal(changed[0].editor_speaker, null)
    assert.equal(changed[0].dialogue_speaker, null)
})

test('project maps can supply identities; default narrator, stale attribution and unrelated voices cannot', () => {
    const rows = [row('続き。', 'narrator'), { ...row('changed', 'adam', 'stale'), editor_speaker: { name: 'stale', text: 'old' } }]
    const sources = [{ voice_map: { '仙太郎': 'adam', '次郎': 'narrator' }, voice_id: 'narrator' }]
    const changed = assignSpeakerVoice(rows, 0, 'adam', 'Adam', false, speakersFor(rows), { voiceSources: sources, characters: [{ name: '仙太郎', gender: 'male' }] })
    assert.equal(changed[0].editor_speaker.name, '仙太郎')
    assert.equal(changed[0].editor_speaker.gender, 'male')
    for (const id of ['narrator', 'unknown']) assert.equal(assignSpeakerVoice(rows, 0, id, id, false, speakersFor(rows), { voiceSources: sources })[0].dialogue_kind, 'narration')
})

test('changing an existing character actor preserves identity and all-speaker scope', () => {
    const rows = [row('一。', 'old', '兄'), row('二。', 'old', '兄'), row('三。', 'adam', '弟')]
    const changed = assignSpeakerVoice(rows, 0, 'adam', 'Adam', true, speakersFor(rows))
    assert.deepEqual(changed.map(r => r.voice_id), ['adam', 'adam', 'adam'])
    assert.equal(changed[0].editor_speaker.name, '兄')
    assert.equal(changed[2], rows[2])
})

for (const edited of [false, true]) test(`scene 64 uncertain-speaker annotation retains middle dialogue, including recovered source alignment (${edited})`, () => {
    const spoken = '開けろ。父をだまして、三千両も取り上げたそうだな。この悪女め。役人に突き出してやる。金を返せ'
    const source = (edited ? '別の導入。\\n\\n' : '兄弟は怒鳴りました。') + '「' + spoken + '」。お鈴は身をこわばらせました。'
    const start = Array.from(source.slice(0, source.indexOf(spoken))).length
    const annotations = { version: 1, source: 'codex-ai', scenes: [{ scene_number: 64, source_text: source, spans: [{ start, end: start + Array.from(spoken).length, text: spoken, status: 'uncertain', speaker: 'untrusted guess' }] }] }
    const rows = [row('兄弟は怒鳴りました。', 'narrator'), row('「開けろ。父をだまして、', 'adam', '仙太郎'), row('三千両も取り上げたそうだな。', 'adam'), row('この悪女め。役人に突き出してやる。', 'harry'), row('金を返せ」。', 'harry', '次郎'), row('お鈴は身をこわばらせました。', 'narrator')]
    const parts = mapDialogueAnnotations(rows, annotations)
    for (const i of [1, 2, 3, 4]) { assert.ok(parts.get(i)?.some(p => p.dialogue)); assert.ok(parts.get(i).every(p => !p.speaker)) }
    for (const i of [0, 5]) assert.ok(!parts.get(i)?.some(p => p.dialogue))
    const classify = (r, i) => r.dialogue_override ?? !!parts.get(i)?.some(p => p.dialogue)
    assert.equal(subtitleTtsReadiness(rows, classify, 'narrator').ready, true, 'Middle dialogue no longer creates false narration overlaps')
    const confirmed = assignSpeakerVoice(rows, 2, 'adam', 'Adam', false, speakersFor(rows))
    const reopened = splitSubtitleDialogueBlocks(confirmed, annotations, true, 100)
    const target = reopened.find(r => r.text === rows[2].text)
    assert.equal(target.editor_speaker.name, '仙太郎')
    assert.equal(target.dialogue_speaker, '仙太郎')
    assert.equal(target.start_num, 1)
})

test('the real row voice handler persists attribution and opens speaker editor only for ambiguity', async () => {
    for (const ambiguous of [false, true]) {
        const rows = [row('続き。', 'narrator'), row('一。', 'adam', '兄'), ...(ambiguous ? [row('二。', 'adam', '弟')] : [])]
        let saved, editor, stopped = false
        const context = { speechSubtitlesRef: { current: rows }, localSubtitles: [], isPlayingPreview: true, stopVrewPlayback: () => { stopped = true },
            selectedProject: { project: { project_payload: {} } }, mapDialogueAnnotations, subtitleSpeaker, assignSpeakerVoice,
            speakerCharacters: [], currentLocale: 'ko', speakerNameTranslations: {}, characterVoices: {}, voiceNameById: new Map([['adam', 'Adam']]),
            markVrewSegmentStale: () => {}, persistVrewVoiceSubtitles: async value => { saved = JSON.parse(JSON.stringify(value)) }, setSpeakerEditorIndex: i => { editor = i } }
        const handler = extract('    const applySubtitleSpeakerVoice =', '    const saveSubtitleSpeaker =', 'applySubtitleSpeakerVoice', context)
        await handler(0, 'adam', false)
        assert.ok(stopped)
        assert.equal(saved[0].dialogue_override, true)
        assert.equal(saved[0].editor_speaker?.name, ambiguous ? undefined : '兄')
        assert.equal(editor, ambiguous ? 0 : undefined)
    }
})
