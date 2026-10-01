import assert from 'node:assert/strict'
import { generateSynchronizedSubtitles, repairSubtitleItemQuoteBoundaries } from '../lib/stdSubtitles'
import { mapDialogueAnnotations, splitSubtitleDialogueBlocks } from '../lib/stdDialogueAnnotations'
import { normalizeSubtitleFragments, isSubtitleClosingPunctuation } from '../lib/stdSubtitleFragments'
import { alignedNarrationSubtitles } from '../lib/stdPreviewAudio'

const text = '「稽古が済んだら、町へ寄るとよい。きれいな帯でも、簪でも、気に入ったものを買っておいで」。お鈴は、それまでの眠そうな顔をぱっと明るくしました。「本当に。ありがとう」。'
const spoken = ['稽古が済んだら、町へ寄るとよい。きれいな帯でも、簪でも、気に入ったものを買っておいで', '本当に。ありがとう']
const annotations = { version: 1, source: 'codex-ai', scenes: [{ scene_number: 1, source_text: text,
    spans: spoken.map((speech, i) => ({ start: text.indexOf(speech), end: text.indexOf(speech) + speech.length,
        text: speech, status: 'confirmed', speaker: i ? 'お鈴' : '大五郎' })) }] }

for (const annotation of [annotations, undefined, { ...annotations, scenes: [{ ...annotations.scenes[0], source_text: text.replace('ありがとう', 'ありがとう、ご隠居さん') }] }]) {
    const generated = generateSynchronizedSubtitles(text, [{ scene_number: 1, scene_text: text }], 20, annotation)
    const displayed = splitSubtitleDialogueBlocks(generated, annotation)
    assert.equal(displayed.map(s => s.text).join(''), text)
    assert.ok(displayed.every(s => !isSubtitleClosingPunctuation(s.text)), 'Full generation and dialogue classification must not recreate a punctuation-only row')
    assert.deepEqual(splitSubtitleDialogueBlocks(displayed, annotation), displayed, 'Reopening saved rows must be idempotent')
    if (annotation) {
        assert.ok([...mapDialogueAnnotations(displayed, annotation).values()].flat()
            .some(part => part.speaker === 'お鈴'), 'Attaching Japanese punctuation must preserve the female speaker, including edited scripts')
    }
}

const saved = ['「稽古が済んだら、町へ寄るとよい。', 'きれいな帯でも、簪でも、', '気に入ったものを買っておいで」', '。', 'お鈴は、', 'それまでの眠そうな顔をぱっと明るくしました。', '「本当に。ありがとう」', '。']
    .map((text, index) => ({ id: `saved-${index}`, text, scene_number: 25, start_num: 132 + index,
        end_num: 133 + index, voice_id: index === 6 ? 'female' : 'male', audio_url: `audio-${index}` }))
const repaired = splitSubtitleDialogueBlocks(saved, undefined)
assert.equal(repaired.length, 6)
assert.equal(repaired[2].text, saved[2].text + '。')
assert.equal(repaired[2].end_num, saved[3].end_num)
assert.equal(repaired[5].voice_id, 'female', 'The punctuation row must not replace the preceding speaker')
assert.equal(repaired[5].audio_url, 'audio-6', 'Punctuation repair preserves existing spoken audio')
assert.equal(repaired.map(s => s.text).join(''), saved.map(s => s.text).join(''))
assert.deepEqual(saved[3].text, '。', 'Do not mutate source records')

const narrationTimeline = saved.map((s, i) => ({ text: s.text, start: i, end: i + 1, voice_id: s.voice_id }))
const playback = alignedNarrationSubtitles(repaired, narrationTimeline)
assert.ok(playback, 'Previously recorded full narration remains usable after punctuation repair')
assert.equal(playback[2].end_num, 4)
assert.equal(playback[5].end_num, 8)
assert.equal(alignedNarrationSubtitles([{ ...repaired[0], text: 'different text' }], narrationTimeline), null)

assert.equal(normalizeSubtitleFragments([
    { text: '前の文', scene_number: 1 }, { text: '。', scene_number: 2 },
]).length, 2, 'Never move punctuation across scene boundaries')
const quoteRepair = repairSubtitleItemQuoteBoundaries([
    { text: '「本当に。ありがとう」。', scene_number: 25, start_num: 0, end_num: 1 },
])
assert.equal(quoteRepair.length, 1)
assert.equal(quoteRepair[0].text, '「本当に。ありがとう」。')
console.log('PASS: screenshot scene 25, fresh generation, saved reload, AI dialogue boundaries and recorded narration alignment')
