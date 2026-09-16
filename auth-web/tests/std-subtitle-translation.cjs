const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const vm = require('node:vm')

const source = fs.readFileSync(require.resolve('../lib/stdSubtitleTranslation.ts'), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const moduleBox = { exports: {} }
vm.runInNewContext(js, { module: moduleBox, exports: moduleBox.exports, require })

const { buildSubtitleTranslationPrompt, isSubtitleTranslationLanguage, parseStrictTranslationResponse, translationMapFromBlocks } = moduleBox.exports
const sourceBlocks = [{ id: 'b0', text: '그가 말했다. "가지 마."' }, { id: 'b1', text: '비가 내렸다.' }]
for (const [language, name] of [['en', 'English'], ['vi', 'Vietnamese'], ['th', 'Thai']]) {
    assert.equal(isSubtitleTranslationLanguage(language), true)
    const prompt = buildSubtitleTranslationPrompt(sourceBlocks, language)
    assert.match(prompt, new RegExp(name))
    assert.match(prompt, /Never merge, split, summarize/)
    assert.match(prompt, /Preserve direct speech as direct speech/)
}
assert.equal(isSubtitleTranslationLanguage('ko'), false)

const parsed = parseStrictTranslationResponse(JSON.stringify({ translations: [
    { id: 'b0', translation: 'เขาพูดว่า “อย่าไป”' },
    { id: 'b1', translation: 'ฝนตก' },
] }), sourceBlocks)
assert.equal(parsed.length, 2)
assert.throws(() => parseStrictTranslationResponse('{"translations":[{"id":"b0","translation":"x"}]}', sourceBlocks), /every subtitle block/)

const map = translationMapFromBlocks([{ index: 0, source_text: sourceBlocks[0].text, translated_text: parsed[0].translation }])
assert.equal(Object.values(map)[0], parsed[0].translation)
console.log('std subtitle translation tests passed')

const { remapSubtitleTranslations, remapSubtitleTranslationMap, subtitleTranslationKey } = moduleBox.exports
const oldTexts = ['반복', '내가 잘못했다.', '겁이 나서 그랬어.', '반복', ...Array.from({ length: 312 }, (_, i) => `정상 문장 ${i}`)]
const saved = oldTexts.map((source_text, index) => ({ index, source_text, translated_text: `태국어 원본 ${index}` }))
const merged = [oldTexts[0], oldTexts[1] + ' ' + oldTexts[2], ...oldTexts.slice(3)]
const aligned = remapSubtitleTranslations(saved, merged.map((source_text, index) => ({ index, source_text })))
assert.equal(aligned.length, merged.length - 1)
assert.equal(aligned[1].translated_text, '태국어 원본 3', 'Repeated sentences must consume separate original translations')
const display = remapSubtitleTranslationMap(translationMapFromBlocks(saved), merged.map(text => ({ text })))
assert.equal(display[subtitleTranslationKey(1, merged[1])], undefined, 'Only the merged block waits for translation')
for (let index = 2; index < merged.length; index++) {
    assert.equal(display[subtitleTranslationKey(index, merged[index])], saved[index + 1].translated_text)
}
const split = ['반복', '내가', '잘못했다.', ...oldTexts.slice(2)]
const splitMap = translationMapFromBlocks(remapSubtitleTranslations(saved, split.map((source_text, index) => ({ index, source_text }))))
assert.equal(splitMap[subtitleTranslationKey(4, '반복')], saved[3].translated_text)
assert.equal(Object.keys(remapSubtitleTranslationMap({}, merged.map(text => ({ text })))).length, 0)
console.log('subtitle merge/split preserves every unchanged translation before any API response')

// Execute the route's cache selection so the regression also covers API input.
const route = fs.readFileSync(require.resolve('../app/api/std/projects/[projectId]/subtitle-translations/route.ts'), 'utf8')
const selection = route.slice(route.indexOf('    const cachedBlocks ='), route.indexOf('    if (missing.length > 0)'))
const selectMissing = new Function('project', 'targetLanguage', 'blocks', 'translationMapFromBlocks', 'remapSubtitleTranslations', 'subtitleTranslationKey',
    ts.transpile(selection + '\nreturn missing', { target: ts.ScriptTarget.ES2020 }))
const missing = selectMissing({ project_payload: { subtitle_translations: { th: { blocks: saved } } } }, 'th',
    merged.map((source_text, index) => ({ index, source_text })), translationMapFromBlocks, remapSubtitleTranslations, subtitleTranslationKey)
assert.deepEqual(missing, [{ index: 1, source_text: merged[1] }])
console.log('API translates only the merged sentence in a 316-block project')
