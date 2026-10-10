const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const source = fs.readFileSync(path.join(__dirname, '../lib/topicUiText.ts'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const copy = {}
new Function('exports', compiled)(copy)

assert.equal(copy.topicUiText('ko', '日本昔話'), '일본 옛날이야기')
assert.equal(copy.topicUiText('en', '총 {count}개 씬 구조', { count: 100 }), '100 scenes total')
assert.equal(copy.topicUiText('vi', '이 주제로 작업 시작'), 'Bắt đầu với chủ đề này')
assert.equal(copy.topicUiText('th', '{count}분 롱폼', { count: 21 }), 'วิดีโอยาว 21 นาที')
console.log('PASS: topic cards and claim modal copy follow the active locale')
