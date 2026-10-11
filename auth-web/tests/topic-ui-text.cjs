const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const copy = require('./load-ts-module.cjs')(path.join(__dirname, '../lib/topicUiText.ts'))

assert.equal(copy.topicUiText('ko', '日本昔話'), '일본 옛날이야기')
assert.equal(copy.topicUiText('en', '총 {count}개 씬 구조', { count: 100 }), '100 scenes total')
assert.equal(copy.topicUiText('vi', '이 주제로 작업 시작'), 'Bắt đầu với chủ đề này')
assert.equal(copy.topicUiText('th', '{count}분 롱폼', { count: 21 }), 'วิดีโอยาว 21 นาที')
console.log('PASS: topic cards and claim modal copy follow the active locale')
