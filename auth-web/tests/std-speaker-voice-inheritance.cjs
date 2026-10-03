const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const exportsBox = {}
new Function('exports', ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../lib/stdSpeakerAssignment.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(exportsBox)
const { confirmSubtitleSpeaker, subtitleSpeaker } = exportsBox
const speaker = (name, gender = 'male') => ({ name, gender, label: `${name} (localized display only)` })
const row = (id, name, voiceId, extras = {}) => ({
    id, text: `「${id}の台詞。」`, scene_number: Number(id.replace(/\D/g, '')) || 1,
    start_num: 12.25, end_num: 14.75, start_time: '12.25', end_time: '14.75',
    voice_direction: `direction-${id}`, volume: 85,
    audio_asset_id: `audio-${id}`, audio_url: `/audio/${id}`, audio_duration: 2.5,
    ...(name ? { editor_speaker: { name, gender: 'male', text: `「${id}の台詞。」` } } : {}),
    ...(voiceId !== undefined ? { voice_id: voiceId, voice_name: `Saved ${voiceId}` } : {}),
    ...extras,
})
const speakersFor = rows => rows.map(item => item.dialogue_override === false ? null : subtitleSpeaker(item, undefined, []))
const catalog = new Map([['actor-sentaro', 'Sentaro actor'], ['explicit-actor', 'Explicit actor']])
function confirm(rows, name = '仙太郎', voices = catalog, sources = [], speakers = speakersFor(rows)) {
    return confirmSubtitleSpeaker(rows, 0, name, 'male', speakers, voices, sources)
}
function unchangedSpeech(actual, before) {
    const editorialKeys = new Set(['editor_speaker', 'voice_id', 'voice_name'])
    const speech = value => Object.fromEntries(Object.entries(value).filter(([key]) => !editorialKeys.has(key)))
    assert.deepEqual(speech(actual), speech(before), 'Text, times, direction, audio and other metadata are preserved')
}

test('confirming the pending Sentaro row inherits the existing actor across scenes and fills only empty peers', () => {
    const rows = [row('pending8'), row('known31', '仙太郎'), row('donor60', '仙太郎', 'actor-sentaro'), row('other61', 'お鈴', 'actor-osuzu')]
    const original = structuredClone(rows)
    const result = confirm(rows)
    assert.equal(result.voiceId, 'actor-sentaro')
    assert.equal(result.conflict, false)
    assert.deepEqual(result.subtitles.map(item => item.voice_id), ['actor-sentaro', 'actor-sentaro', 'actor-sentaro', 'actor-osuzu'])
    assert.equal(result.subtitles[0].voice_name, 'Sentaro actor')
    assert.equal(result.subtitles[1].voice_name, 'Sentaro actor')
    assert.equal(result.subtitles[2].voice_name, 'Saved actor-sentaro', 'An already assigned peer keeps its voice label')
    for (const index of [0, 1, 2]) assert.deepEqual(result.subtitles[index].editor_speaker, { name: '仙太郎', gender: 'male', text: rows[index].text })
    assert.equal(result.subtitles[3], rows[3])
    result.subtitles.forEach((item, index) => unchangedSpeech(item, rows[index]))
    assert.deepEqual(rows, original, 'The input snapshot is never mutated')
})

test('unrelated voices, narration overrides and stale editor attribution never supply a character voice', () => {
    const rows = [row('pending1'), row('other2', 'お鈴', 'wrong-other'),
        row('narrator3', '仙太郎', 'gemini:Achernar', { dialogue_override: false }),
        row('stale4', '仙太郎', 'wrong-stale', { editor_speaker: { name: '仙太郎', gender: 'male', text: 'old text' } })]
    const result = confirm(rows, '仙太郎', catalog, [], [null, speaker('お鈴'), speaker('仙太郎'), speaker('仙太郎')])
    assert.equal(result.voiceId, null)
    assert.equal(result.conflict, false)
    assert.equal(result.subtitles[0].voice_id, undefined)
    assert.equal(result.subtitles[0].editor_speaker.name, '仙太郎')
})

test('empty donor voices are ignored, and every nonempty donor must agree before inheritance', () => {
    const rows = [row('pending1'), row('empty2', '仙太郎', ''), row('space3', '仙太郎', '   '),
        row('donor4', '仙太郎', 'actor-sentaro'), row('donor5', '仙太郎', 'actor-sentaro')]
    const result = confirm(rows)
    assert.equal(result.voiceId, 'actor-sentaro')
    assert.equal(result.conflict, false)
    for (const index of [0, 1, 2]) assert.equal(result.subtitles[index].voice_id, 'actor-sentaro')
})

test('conflicting peers confirm attribution without guessing or overwriting assigned voices', () => {
    const rows = [row('pending1', undefined, 'target-existing'), row('donor2', '仙太郎', 'actor-a'),
        row('donor3', '仙太郎', 'actor-b'), row('empty4', '仙太郎')]
    const result = confirm(rows, '仙太郎', catalog, [{ voice_map: { '仙太郎': 'old-saved-map' }, voice_id: 'default' }])
    assert.equal(result.voiceId, null)
    assert.equal(result.conflict, true)
    assert.deepEqual(result.subtitles.map(item => item.voice_id), ['target-existing', 'actor-a', 'actor-b', undefined])
    assert.equal(result.subtitles[0].editor_speaker.name, '仙太郎')
})

test('an explicit current-project character map resolves conflicting donors and preserves their per-row overrides', () => {
    const rows = [row('pending1'), row('donor2', '仙太郎', 'actor-a'), row('donor3', '仙太郎', 'actor-b'), row('empty4', '仙太郎')]
    const sources = [{ voice_map: { '仙太郎': 'old-map' }, voice_id: 'default' },
        { voice_map: { '仙太郎': 'explicit-actor' }, explicit: true }]
    const result = confirm(rows, '仙太郎', catalog, sources)
    assert.equal(result.voiceId, 'explicit-actor')
    assert.equal(result.conflict, false)
    assert.deepEqual(result.subtitles.map(item => item.voice_id), ['explicit-actor', 'actor-a', 'actor-b', 'explicit-actor'])
    assert.equal(result.subtitles[0].voice_name, 'Explicit actor')
    rows.forEach((item, index) => unchangedSpeech(result.subtitles[index], item))
})

test('saved voice maps are only a fallback and skip entries equal to their default narrator', () => {
    const rows = [row('pending1')]
    const sources = [{ voice_map: { '仙太郎': 'google_kr' }, voice_id: 'google_kr' },
        { voice_map: { '仙太郎': 'saved-actor' }, voice_id: 'google_kr' }]
    assert.equal(confirm(rows, '仙太郎', catalog, sources).voiceId, 'saved-actor')
    assert.equal(confirm(rows, '仙太郎', catalog, sources.slice(0, 1)).voiceId, null)
    const withDonor = [...rows, row('donor2', '仙太郎', 'actor-sentaro')]
    assert.equal(confirm(withDonor, '仙太郎', catalog, sources).voiceId, 'actor-sentaro')
})

test('renaming the target uses its new character peers; without peers it retains its existing voice', () => {
    const target = row('target1', '大五郎', 'old-role-actor')
    const renamed = confirm([target, row('donor2', '仙太郎', 'actor-sentaro')])
    assert.equal(renamed.subtitles[0].voice_id, 'actor-sentaro')
    assert.equal(renamed.subtitles[0].editor_speaker.name, '仙太郎')
    unchangedSpeech(renamed.subtitles[0], target)
    const alone = confirm([target])
    assert.equal(alone.voiceId, null, 'The target itself is never a donor for the new identity')
    assert.equal(alone.subtitles[0].voice_id, 'old-role-actor')
    assert.equal(alone.subtitles[0].voice_name, 'Saved old-role-actor')
})

test('canonical original names match exactly; localized labels and similar names are not voice aliases', () => {
    const rows = [row('pending1'), row('alias2', '仙太郎 (센타로)', 'localized-label-actor'), row('alias3', '센타로', 'translated-name-actor')]
    const sources = [{ voice_map: { '仙太郎 (센타로)': 'map-label-actor', '仙太郎2': 'other-name-actor' } }]
    assert.equal(confirm(rows, '仙太郎', catalog, sources).voiceId, null)
    const exact = [...rows, row('exact4', '仙太郎', 'actor-sentaro')]
    assert.equal(confirm(exact, '仙太郎', catalog, sources).voiceId, 'actor-sentaro')
})

test('inherited display labels prefer catalog, then matching donor label, then raw voice id', () => {
    const rows = [row('pending1'), row('donor2', '仙太郎', 'actor-sentaro')]
    assert.equal(confirm(rows).subtitles[0].voice_name, 'Sentaro actor')
    assert.equal(confirm(rows, '仙太郎', new Map()).subtitles[0].voice_name, 'Saved actor-sentaro')
    const noLabel = [rows[0], { ...rows[1], voice_name: '' }]
    assert.equal(confirm(noLabel, '仙太郎', new Map()).subtitles[0].voice_name, 'actor-sentaro')
})

test('inherited assignment survives JSON save/reload and becomes a donor for another pending line', () => {
    const initial = [row('pending1'), row('known2', '仙太郎'), row('donor3', '仙太郎', 'pNInz6obpgDQGcFmaJgB')]
    const saved = confirm(initial)
    const reloaded = JSON.parse(JSON.stringify({ project_payload: { subtitles: saved.subtitles } })).project_payload.subtitles
    assert.equal(subtitleSpeaker(reloaded[0], undefined, []).name, '仙太郎')
    assert.equal(reloaded[0].voice_id, 'pNInz6obpgDQGcFmaJgB')
    assert.deepEqual(reloaded[0].editor_speaker, saved.subtitles[0].editor_speaker)
    unchangedSpeech(reloaded[0], initial[0])
    const next = confirm([row('newPending9'), ...reloaded])
    assert.equal(next.voiceId, 'pNInz6obpgDQGcFmaJgB')
    assert.equal(next.subtitles[0].voice_id, 'pNInz6obpgDQGcFmaJgB')
})

test('the page scopes explicit character maps by project and ignores a delayed prior-project setter', () => {
    const page = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
    const from = page.indexOf('    const [characterVoiceState, setCharacterVoiceState]')
    const to = page.indexOf('    const [newCharInput', from)
    assert.ok(from >= 0 && to > from)
    const compiled = ts.transpileModule(page.slice(from, to) + '\nreturn { characterVoices, setCharacterVoices }', {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText
    const render = new Function('selectedProject', 'useState', 'useRef', compiled)
    let state = { projectId: 'project-a', voices: { '仙太郎': 'actor-a' } }
    const projectRef = { current: 'project-a' }
    const useState = () => [state, update => { state = typeof update === 'function' ? update(state) : update }]
    const useRef = () => projectRef
    const first = render({ project: { id: 'project-a' } }, useState, useRef)
    assert.deepEqual(first.characterVoices, { '仙太郎': 'actor-a' })
    const second = render({ project: { id: 'project-b' } }, useState, useRef)
    assert.deepEqual(second.characterVoices, {}, 'Identical character names in another project cannot inherit this map')
    second.setCharacterVoices(previous => ({ ...previous, '仙太郎': 'actor-b' }))
    const confirmedB = state
    first.setCharacterVoices(previous => ({ ...previous, '仙太郎': 'late-actor-a' }))
    assert.equal(state, confirmedB, 'A delayed project-A callback leaves project-B state untouched')
    assert.deepEqual(render({ project: { id: 'project-b' } }, useState, useRef).characterVoices, { '仙太郎': 'actor-b' })
})
