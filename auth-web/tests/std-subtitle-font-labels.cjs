const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), ts = require('typescript')
const catalog = require('../public/fonts/catalog.json')
const source = ts.transpileModule(fs.readFileSync('lib/stdSubtitleFontLabels.ts', 'utf8'), { compilerOptions: { module: 1 } }).outputText
const exportsForTest = {}; new Function('exports', source)(exportsForTest)
const label = exportsForTest.subtitleFontLabel

test('every subtitle font has a localized display name in every supported language', () => {
  for (const font of [...Object.keys(catalog), 'Malgun Gothic']) {
    for (const locale of ['ko', 'en', 'vi', 'th']) assert.ok(label(font, locale).trim(), `${font}: ${locale}`)
  }
  assert.match(label('NotoSansJP-Regular', 'en'), /Japanese/)
  assert.match(label('NotoSansJP-Regular', 'vi'), /Nhật/)
  assert.match(label('NotoSansJP-Regular', 'th'), /ญี่ปุ่น/)
  assert.equal(label('Unknown font', 'th'), 'Unknown font')
})
