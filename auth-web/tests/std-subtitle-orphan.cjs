const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')
function load(file) {
    const exports = {}
    const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText
    new Function('exports', 'require', compiled)(exports, name => load(path.resolve(path.dirname(file), `${name}.ts`)))
    return exports
}
const { restoreSavedSubtitleSnapshot } = load(path.resolve(__dirname, '../lib/stdSubtitleSnapshot.ts'))
const { splitTextToSingleLineChunks } = load(path.resolve(__dirname, '../lib/stdSubtitles.ts'))
const { alignedNarrationSubtitles } = load(path.resolve(__dirname, '../lib/stdPreviewAudio.ts'))
test('scene 77 saved negative ending is joined on reopening, preserving speaker and recorded boundaries', () => {
    const rows = ['「今の私が話せるというだけで、', 'すべてをお決めいただこうとは思いませ', 'ん」'].map((text, index) => ({
        id: `row-${index}`, text, scene_number: 77, voice_id: 'actor', dialogue_speaker: '大五郎',
        start_num: index, end_num: index + 1,
    }))
    const repaired = restoreSavedSubtitleSnapshot(rows, () => [])
    assert.equal(repaired.length, 2)
    assert.equal(repaired[1].text, rows[1].text + rows[2].text)
    assert.equal(repaired[1].start_num, 1)
    assert.equal(repaired[1].end_num, 3)
    assert.equal(repaired[1].voice_id, 'actor')
    assert.deepEqual(restoreSavedSubtitleSnapshot(repaired, () => []), repaired)
    assert.ok(alignedNarrationSubtitles(repaired, rows.map(row => ({ text: row.text, voice_id: row.voice_id, start: row.start_num, end: row.end_num }))))
    assert.equal(rows.length, 3)
})
test('fresh generation never strands a one-character ending with its closing quote', () => {
    const text = '「今の私が話せるというだけで、すべてをお決めいただこうとは思いません」'
    for (const limit of [18, 20, 22]) {
        const chunks = splitTextToSingleLineChunks(text, limit, { dialogue: true })
        assert.equal(chunks.join(''), text)
        assert.ok(chunks.every(chunk => !/^[ぁ-んァ-ヶ][」』。]*$/u.test(chunk)))
    }
})
test('short reactions belonging to another speaker or scene remain separate', () => {
    for (const change of [{ scene_number: 78 }, { voice_id: 'another' }, { dialogue_speaker: 'お鈴' }]) {
        const rows = [{ text: 'まだ話していませ', scene_number: 77, voice_id: 'actor', dialogue_speaker: '大五郎' },
            { text: 'ん」', scene_number: 77, voice_id: 'actor', dialogue_speaker: '大五郎', ...change }]
        assert.equal(restoreSavedSubtitleSnapshot(rows, () => []).length, 2)
    }
})
