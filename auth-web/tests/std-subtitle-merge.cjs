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
    let selection = [], saved, selectedIndex, stale, translationRequest, message = ''
    const anchor = {current: null}
    const select = compileBetween('    const selectSubtitlePreview =', '    const persistVrewVoiceSubtitles', 'selectSubtitleBlock', {
        localSubtitles: rows, subtitleBlockSelectionAnchorRef: anchor,
        setSelectedSubtitleBlockIndexes: value => {selection = typeof value === 'function' ? value(selection) : value}, setMessage: value => { message = value },
        setSelectedSubIndex: value => {selectedIndex = value}, setPlaybackTime: () => {},
        stopVrewPlayback: () => {}, setPreviewTransition: () => {},
    })
    select(3, false); select(4, true)
    assert.deepEqual(selection, [3, 4])
    select(3, false); select(4, false, true)
    assert.deepEqual(selection, [3, 4], 'Ctrl/Command-click adds the second row rather than replacing the first')
    select(3, false, true)
    assert.deepEqual(selection, [4], 'Ctrl/Command-click can deselect a row')
    select(3, false); select(4, true)
    const mergeContext = {
        selectedSubtitleBlockIndexes: selection, localSubtitles: rows, ui: text => text,
        subtitleTranslationControllerRef: { current: null }, subtitleTranslationRequestRef: { current: '' }, setTranslatingSubtitleLanguage: () => {},
        subtitleReviewLocale: 'th', translateSubtitleBlocks: (...args) => { translationRequest = args },
        isSubtitleDialogue: () => true, subtitleSpeakers: {}, aiDialogueParts: new Map([[3, [{dialogue: true, speaker: '노인'}]], [4, [{dialogue: true, speaker: '노인'}]]]),
        currentNav: 'subtitle_vrew', isPlayingPreview: false, stopVrewPlayback: () => {},
        markVrewSegmentStale: item => {stale = item}, setSelectedSubIndex: value => {selectedIndex = value},
        setSelectedSubtitleBlockIndexes: value => {selection = value}, subtitleBlockSelectionAnchorRef: anchor,
        persistVrewVoiceSubtitles: async value => {saved = value; return true}, setMessage: value => { message = value },
    }
    const mergeWith = changes => compileBetween('    const mergeSelectedSubtitleBlocks =', '    const splitSelectedSubtitleBlock', 'mergeSelectedSubtitleBlocks', { ...mergeContext, ...changes })
    const merge = mergeWith({})
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
    saved = undefined
    await mergeWith({ selectedSubtitleBlockIndexes: [3, 5] })()
    assert.equal(saved, undefined)
    assert.match(message, /사이에 빠진 자막/)
    await mergeWith({ isSubtitleDialogue: (_, index) => index === 3 })()
    assert.equal(saved, undefined)
    assert.match(message, /같은 화자/)

    // Render the actual workspace status element, so rejected merges are not
    // silently sent to the unrelated login/BGM messages again.
    const ast = ts.createSourceFile('page.tsx', page, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    let status
    let numberClick
    const visit = node => {
        if (ts.isJsxElement(node) && node.openingElement.attributes.properties.some(p => p.name?.getText(ast) === 'data-subtitle-action-status')) status = node
        if (ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === 'button'
            && node.openingElement.attributes.properties.some(p => p.name?.getText(ast) === 'aria-pressed')
            && node.getText(ast).includes('selectSubtitleBlock(item.subtitleIndex')) {
            numberClick = node.openingElement.attributes.properties.find(p => p.name?.getText(ast) === 'onClick').initializer.expression
        }
        ts.forEachChild(node, visit)
    }
    visit(ast)
    assert(numberClick)
    const click = index => new Function('selectSubtitleBlock', 'item', ts.transpile(`return (${numberClick.getText(ast)})`, {target:7}))(select, {subtitleIndex:index})
    selection = []
    click(3)({ stopPropagation() {}, shiftKey:false })
    click(4)({ stopPropagation() {}, shiftKey:false })
    assert.deepEqual(selection, [3, 4], 'Clicking subtitle numbers without keyboard modifiers must keep both selected')
    assert(status, 'Subtitle actions need a visible status inside the workspace')
    const code = ts.transpileModule(`const result = (${status.getText(ast)}); return result`, {compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText
    const element = new Function('require', 'exports', 'message', code)(require, {}, message)
    const html = require('react-dom/server').renderToStaticMarkup(element)
    assert.match(html, /role="status"/)
    assert(html.includes(message), 'The reason the merge was rejected must appear in the subtitle workspace')
    console.log('PASS: Shift selection, merged text/timing, scene count 8 to 7, preserved following rows and stale audio')
}
main().catch(error => {console.error(error); process.exitCode = 1})
