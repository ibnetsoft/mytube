const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const vm = require('node:vm')

const source = fs.readFileSync(require.resolve('../lib/stdSubtitleTranslation.ts'), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const moduleBox = { exports: {} }
vm.runInNewContext(js, { module: moduleBox, exports: moduleBox.exports, require })

const { buildThaiSubtitleTranslationPrompt, parseStrictTranslationResponse, translationMapFromBlocks } = moduleBox.exports
const sourceBlocks = [{ id: 'b0', text: '그가 말했다. "가지 마."' }, { id: 'b1', text: '비가 내렸다.' }]
const prompt = buildThaiSubtitleTranslationPrompt(sourceBlocks)
assert.match(prompt, /Never merge, split, summarize/)
assert.match(prompt, /Preserve direct speech as direct speech/)

const parsed = parseStrictTranslationResponse(JSON.stringify({ translations: [
    { id: 'b0', translation: 'เขาพูดว่า “อย่าไป”' },
    { id: 'b1', translation: 'ฝนตก' },
] }), sourceBlocks)
assert.equal(parsed.length, 2)
assert.throws(() => parseStrictTranslationResponse('{"translations":[{"id":"b0","translation":"x"}]}', sourceBlocks), /every subtitle block/)

const map = translationMapFromBlocks([{ index: 0, source_text: sourceBlocks[0].text, translated_text: parsed[0].translation }])
assert.equal(Object.values(map)[0], parsed[0].translation)
console.log('std subtitle translation tests passed')
