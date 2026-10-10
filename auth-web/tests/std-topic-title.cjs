const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const source = fs.readFileSync(path.join(__dirname, '../lib/stdTopicTitle.ts'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const title = {}
new Function('exports', 'require', compiled)(title, () => ({}))

assert.equal(title.localizedTopicTitle({ generated_title: '封をほどく朝' }, 'ko'), '봉투를 푸는 아침')
assert.match(title.localizedTopicTitle({ generated_title: '木曽路、藍の灯 | 店を守るため、女がたどった記録' }, 'en'), /Kiso Road/)
assert.equal(title.localizedTopicTitle({ generated_title: '原題', topic_th: 'ชื่อภาษาไทย' }, 'th'), 'ชื่อภาษาไทย')
assert.equal(title.localizedTopicTitle({ generated_title: '原題', progress_payload: { title_translations: { en: 'English title' } } }, 'en'), 'English title')
assert.equal(title.localizedTopicTitle({ generated_title: 'Same', topic_en: 'Same' }, 'en'), '')
console.log('PASS: topic titles use saved locale translations with prepared Japanese fallbacks')
