const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const output = {}
new Function('exports', ts.transpile(fs.readFileSync('auth-web/lib/stdTtsErrorMessage.ts', 'utf8'), { module: 1, target: 7 }))(output)
const format = output.formatTtsErrorMessage

const googleQuota = 'TTS generation failed (prepare_saved_segments): 자막 31번: Google 음성 서버의 요청 한도에 도달했습니다. (429 / RESOURCE_EXHAUSTED) Quota exceeded for aiplatform.googleapis.com with base model: gemini-2.5-flash-tts.'
const message = format(googleQuota)
assert(message.startsWith(googleQuota), 'Retain the actual provider, failed subtitle, and upstream details')
assert.match(message, /ElevenLabs 잔여 크레딧과는 별개/)
assert(!message.includes('ElevenLabs 크레딧/쿼터가 부족'))
for (const error of ['Google 인증 서버 오류 (401): unauthorized API key', 'Voice Studio Google Cloud billing credit unavailable (403)', 'gemini-2.5-flash-tts server timeout (504)']) {
    assert.equal(format(error), error, 'Never relabel a Google authentication/billing/timeout error as ElevenLabs')
}
assert.equal(format('Provider quota_exceeded (429)'), 'Provider quota_exceeded (429)', 'Unknown providers stay unknown')
const eleven = format('자막 42번: ElevenLabs TTS API error: You have 10 credits remaining, while 21 credits are required')
assert.match(eleven, /자막 42번/)
assert.match(eleven, /잔여 크레딧은 10/)
assert.match(eleven, /요청에는 21/)
assert.match(eleven, /키별 사용 한도/)
assert(!eleven.includes('키를 충전'))
assert.match(format('ElevenLabs TTS API error (401): invalid API key'), /ElevenLabs API 키와 사용 권한/)
console.log('PASS: Google quota/auth/billing errors keep their provider and subtitle; unknown quotas stay unknown; ElevenLabs limits retain reported amounts and key scope')
