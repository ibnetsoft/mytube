const assert = require('node:assert/strict')
const { stdUiText } = require('./load-ts-module.cjs')('auth-web/lib/stdUiText.ts')
for (const locale of ['en', 'vi', 'th']) {
  for (const source of ['음성 복구 필요', 'Google 한국어 (무료 TTS)', 'Zoom In · 확대', '자막 {count}개', '{count}줄']) {
    const result = stdUiText(locale, source, { count: 2 })
    assert.notEqual(result, source, `${locale}: ${source}`)
    assert.doesNotMatch(result, /[가-힣]/, `${locale}: ${result}`)
  }
  assert.equal(stdUiText(locale, 'Custom voice name'), 'Custom voice name')
}
assert.equal(stdUiText('ko', 'Google 한국어 (무료 TTS)'), 'Google 한국어 (무료 TTS)')
console.log('PASS: localized subtitle review labels preserve custom voice names')
