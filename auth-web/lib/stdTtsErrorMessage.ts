/** Keep provider identity and the failed subtitle when explaining a TTS error. */
export function formatTtsErrorMessage(errorMessage: string): string {
    const raw = String(errorMessage || 'TTS generation failed')
    const lower = raw.toLowerCase()
    const google = /google|gemini|voice studio|aiplatform|texttospeech/.test(lower)
    const elevenLabs = lower.includes('elevenlabs')

    if (google) {
        if (/quota|resource_exhausted|429|요청 한도/.test(lower)) {
            return `${raw}\nGoogle 음성 API의 요청 한도이며 ElevenLabs 잔여 크레딧과는 별개입니다. 반복되면 Google Cloud의 해당 TTS 모델 할당량을 확인해 주세요.`
        }
        return raw
    }

    if (elevenLabs && /payment_required|payment_issue|failed or incomplete payment|complete the latest invoice/.test(lower)) {
        return `${raw}\nElevenLabs 구독 결제가 실패했거나 완료되지 않아 음성 생성이 차단되었습니다. AIR Studio에 등록된 API 키 계정의 최신 청구서와 결제 상태를 확인해 주세요. 잔여 크레딧이 있어도 결제 문제가 해결되어야 음성을 생성할 수 있습니다.`
    }

    if (elevenLabs && /quota_exceeded|exceeds your quota|credits remaining|insufficient credits|크레딧|quota/.test(lower)) {
        const creditMatch = raw.match(/you have\s+([\d,]+)\s+credits?\s+remaining,\s+while\s+([\d,]+)\s+credits?\s+are required/i)
        const creditDetail = creditMatch
            ? ` API가 보고한 잔여 크레딧은 ${creditMatch[1]}이고, 이번 요청에는 ${creditMatch[2]} 크레딧이 필요합니다.`
            : ''
        return `${raw}\nElevenLabs API 사용 한도에 도달했습니다.${creditDetail} AIR Studio에 등록된 API 키의 계정과 키별 사용 한도를 확인해 주세요.`
    }

    if (/function_invocation_timeout|gateway timeout|504|timeout/.test(lower)) {
        return `${raw}\n서버 음성 생성 시간이 초과되었습니다. 완료된 구간은 저장되어 있으므로 잠시 후 다시 시도해 주세요.`
    }

    if (elevenLabs && /401|unauthorized|api key/.test(lower)) {
        return `${raw}\nAIR Studio에 등록된 ElevenLabs API 키와 사용 권한을 확인해 주세요.`
    }

    return raw
}
