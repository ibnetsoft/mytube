const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
function compileBetween(start, end, name, context) {
    const code = page.slice(page.indexOf(start), page.indexOf(end, page.indexOf(start))) + `\nreturn ${name}`
    const js = ts.transpileModule(code, {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText
    return new Function(...Object.keys(context), js)(...Object.values(context))
}
async function main() {
    const rows = Array.from({length: 8}, (_, index) => ({id: `row-${index}`, scene_number: 31, text: index === 3 ? '그' : index === 4 ? '밤에 네 울음이 그리 작더니.' : `문장 ${index}`, start_num: index * 2, end_num: index * 2 + 2, start_time: String(index * 2), end_time: String(index * 2 + 2), voice_id: 'actor'}))
    let selection = [], saved, selectedIndex, stale, translationRequest
    const anchor = {current: null}
    const select = compileBetween('    const selectSubtitleBlock =', '    const persistVrewVoiceSubtitles', 'selectSubtitleBlock', {
        localSubtitles: rows, subtitleBlockSelectionAnchorRef: anchor,
        setSelectedSubtitleBlockIndexes: value => {selection = value}, setMessage: () => {},
        setSelectedSubIndex: value => {selectedIndex = value}, setPlaybackTime: () => {},
    })
    select(3, false); select(4, true)
    assert.deepEqual(selection, [3, 4])
    const merge = compileBetween('    const mergeSelectedSubtitleBlocks =', '    const splitSelectedSubtitleBlock', 'mergeSelectedSubtitleBlocks', {
        selectedSubtitleBlockIndexes: selection, localSubtitles: rows,
        subtitleTranslationControllerRef: { current: null }, subtitleTranslationRequestRef: { current: '' }, setTranslatingSubtitleLanguage: () => {},
        subtitleReviewLocale: 'th', translateSubtitleBlocks: (...args) => { translationRequest = args },
        isSubtitleDialogue: () => true, aiDialogueParts: new Map([[3, [{dialogue: true, speaker: '노인'}]], [4, [{dialogue: true, speaker: '노인'}]]]),
        currentNav: 'subtitle_vrew', isPlayingPreview: false, stopVrewPlayback: () => {},
        markVrewSegmentStale: item => {stale = item}, setSelectedSubIndex: value => {selectedIndex = value},
        setSelectedSubtitleBlockIndexes: value => {selection = value}, subtitleBlockSelectionAnchorRef: anchor,
        persistVrewVoiceSubtitles: async value => {saved = value}, setMessage: () => {},
    })
    await merge()
    assert.equal(saved.length, 7)
    assert.equal(translationRequest, undefined, 'Merging must not call translation')
    assert.equal(saved[3].translation_manual, true, 'Manual translation survives save and reload')
    assert.equal(saved.filter(item => item.scene_number === 31).length, 7)
    assert.equal(saved[3].text, '그 밤에 네 울음이 그리 작더니.')
    assert.equal(saved[3].start_num, 6)
    assert.equal(saved[3].end_num, 10)
    assert.equal(saved[4].id, 'row-5')
    assert.equal(stale, saved[3])
    assert.equal(selectedIndex, 3)
    assert.deepEqual(selection, [3])
    console.log('PASS: Shift selection, merged text/timing, scene count 8 to 7, preserved following rows and stale audio')
}
main().catch(error => {console.error(error); process.exitCode = 1})
