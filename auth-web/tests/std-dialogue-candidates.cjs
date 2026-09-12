const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const source = fs.readFileSync(require('node:path').join(__dirname, '../lib/stdDialogueCandidates.ts'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
const exported = {}
new Function('exports', compiled)(exported)
const detect = texts => exported.detectDialogueCandidates(texts.map(text => ({ text })))
const screenshot = ['느티나무 아래서 며느리가 가쁜 숨을', '고르자 품에 안은 보따리도', '들썩였습니다. 아이 소리냐고 사람들이', '수군거리자 며느리가 답했습니다.', '아이는 살아 있습니다. 함께 온 노인', '곁에서 기다리고 있어요.']
assert.deepEqual([...detect(screenshot).keys()], [4, 5])
const mixed = '며느리가 답했습니다. 아이는 살아 있습니다.'
assert.equal(mixed.slice(detect([mixed]).get(0)[0].start), '아이는 살아 있습니다.')
assert.equal(detect(['그는 답했습니다. 그녀는 고개를 끄덕였습니다. 집으로 돌아갔습니다.']).size, 0)
assert.equal(detect(['오늘은 날씨가 좋습니다. 함께 알아볼까요?']).size, 0)
assert.equal(detect(['엄마, 어디에 있어요?']).size, 1)
assert.equal(detect(['그가 답했습니다. "괜찮아요." 그는 돌아섰습니다.']).size, 0)
assert.equal(detect([]).size, 0)
console.log('PASS: unquoted dialogue, wrapped sentences, mixed rows, narration and explicit quotes')
