const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const moduleExports = {}
new Function('exports', ts.transpile(fs.readFileSync(path.join(__dirname, '../lib/stdActionFeedback.ts'), 'utf8'), { module: 1, target: 7 }))(moduleExports)
const localize = moduleExports.localizeStdActionError

const equivalentErrors = [
    ['Project not found', '프로젝트를 찾을 수 없습니다.'],
    ['Project changed while saving; reload and retry', '자막 저장 중 충돌이 발생했습니다.'],
    ['The script has changed', '대본이 변경되었습니다. 새 대본으로 TTS를 다시 생성한 뒤 렌더링해 주세요.'],
    ['Google voice quota exceeded (429)', 'Google 음성 서버의 요청 한도에 도달했습니다.'],
    ['ElevenLabs quota_exceeded', 'ElevenLabs 크레딧이 부족합니다.'],
    ['Google Cloud billing is disabled', 'Google Cloud 결제 설정으로 음성을 생성하지 못했습니다.'],
    ['Network request failed', '네트워크 연결에 실패했습니다.'],
    ['TTS audio is required before submitting for render', '렌더용 오디오 파일이 없습니다. GCS 저장 정보가 필요합니다.'],
    ['Thumbnail is required before submitting for render', '배경과 문구를 합성한 최종 썸네일을 저장해 주세요.'],
]
const errors = [
    ...equivalentErrors.flat(), 'Project is closed', 'Project has no scenes to render',
    'Some scenes do not have required uploaded assets', 'TTS text is empty',
    'ElevenLabs API key is not configured', 'Google Cloud API permission denied (403)',
    'GCS is not configured for generated scene asset archiving.', '편집 배경과 문구 레이어를 먼저 저장해 주세요.',
    '생성 이미지 24번을 GCS에서 읽을 수 없습니다: missing file',
    '이 음성의 생성 요청이 이미 진행 중이거나 저장 확인이 필요합니다. 잠시 후 다시 시도해 주세요.',
    'Project not found', 'Unauthorized', 'The operation timed out', '알 수 없는 내부 SQL 오류: private_table',
]
for (const locale of ['en', 'th', 'vi']) {
    for (const [english, korean] of equivalentErrors) {
        assert.equal(localize(english, locale, 'submit'), localize(korean, locale, 'submit'), `${locale}: equivalent errors have the same guidance`)
    }
    for (const error of errors) {
        const result = localize(new Error(error), locale, 'submit')
        assert(!/[가-힣]/.test(result), `${locale}: untranslated Korean must not leak: ${result}`)
        assert(!result.includes('private_table'), 'Raw database diagnostics remain outside the notification')
        if (locale === 'th') assert(/[ก-๙]/.test(result), 'Thai mode uses Thai guidance')
        if (locale === 'vi') assert(/[à-ỹ]/.test(result), 'Vietnamese mode uses Vietnamese guidance')
    }
    const quota = localize('자막 42번: ElevenLabs TTS API error: You have 10 credits remaining, while 21 credits are required', locale, 'tts')
    assert.match(quota, /42:/, 'Failed subtitle number is retained')
    assert.match(quota, /10/, 'Reported credit balance is retained')
    assert.match(quota, /21/, 'Reported credit requirement is retained')
    assert.match(quota, /ElevenLabs/, 'Correct provider is retained')
    assert.equal(localize('ElevenLabs TTS API error (401): quota_exceeded', locale, 'tts'), localize('ElevenLabs quota_exceeded', locale, 'tts'), 'Provider quota codes take precedence over its 401 HTTP status')
    const paymentError = '자막 72번: ElevenLabs TTS API error (401): {"detail":{"type":"payment_required","code":"payment_issue","message":"Your subscription has a failed or incomplete payment. Complete the latest invoice to continue usage.","request_id":"private-payment-request"}}'
    const paymentMessage = localize(paymentError, locale, 'tts')
    const paymentGuidance = localize('ElevenLabs payment_issue', locale, 'tts')
    assert.equal(paymentMessage, `${({ en: 'Subtitle', th: 'คำบรรยาย', vi: 'Phụ đề' }[locale])} 72: ${paymentGuidance}`, 'A payment failure keeps the failed subtitle and overrides HTTP 401')
    for (const variant of ['ElevenLabs payment_required', 'ElevenLabs failed or incomplete payment', 'ElevenLabs complete the latest invoice', 'ElevenLabs payment_issue; credits remaining: 88127']) {
        assert.equal(localize(variant, locale, 'tts'), paymentGuidance, 'Payment codes and messages take precedence over quota wording')
    }
    assert.notEqual(paymentGuidance, localize('ElevenLabs quota_exceeded', locale, 'tts'), 'Payment restrictions are distinct from credit quotas')
    assert.notEqual(paymentGuidance, localize('ElevenLabs API key invalid (401)', locale, 'tts'), 'Payment restrictions are distinct from API key errors')
    assert(!/[가-힣]/.test(paymentMessage) && !paymentMessage.includes('private-payment-request'), 'Localized payment notices do not leak raw diagnostics')
    assert.match(paymentGuidance, ({ en: /latest invoice/, th: /ใบแจ้งหนี้ล่าสุด/, vi: /hóa đơn mới nhất/ }[locale]), 'Each language directs the user to the latest invoice')
    assert.match(localize('생성 이미지 24번을 GCS에서 읽을 수 없습니다: {}', locale, 'submit'), /24:/)
    assert.equal(localize({ error: 'Project not found' }, locale, 'submit'), localize('Project not found', locale, 'submit'))
    assert.notEqual(localize('', locale, 'subtitle_save'), localize('', locale, 'tts'), 'Unknown failures use the action-specific fallback')
    assert.notEqual(localize('timeout', locale, 'tts'), localize('timeout', locale, 'submit'), 'Only TTS timeout mentions reusable saved segments')
}
assert.equal(localize('원래 상세한 오류', 'ko', 'submit'), '원래 상세한 오류', 'Korean diagnostics stay unchanged')
assert.equal(localize('Project not found', 'th-TH', 'submit'), localize('Project not found', 'th', 'submit'))
assert.equal(localize(undefined, 'vi', 'subtitle_save'), localize('Unknown error', 'vi', 'subtitle_save'))
console.log('PASS: action errors localize to Thai, Vietnamese, and English without leaking untranslated server details; provider, scene, subtitle, and quota details remain meaningful')
