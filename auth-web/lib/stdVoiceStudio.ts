// Server-only Google Cloud TTS adapter. Never send ADC or project credentials to clients.
import { voiceStudioAuth } from './voiceStudioAuth'
import { createHash, randomUUID } from 'crypto'
import { mkdir, readFile, writeFile, rename } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { voiceStudioName } from './voiceStudioCatalog'

const pending = new Map<string, Promise<Buffer>>()
const SYNTHESIS_URL = 'https://texttospeech.googleapis.com/v1/text:synthesize'
const REQUEST_BUDGET_MS = 180000
const GOOGLE_STATUSES = new Set(['INVALID_ARGUMENT', 'FAILED_PRECONDITION', 'OUT_OF_RANGE', 'UNAUTHENTICATED', 'PERMISSION_DENIED', 'NOT_FOUND', 'ABORTED', 'ALREADY_EXISTS', 'RESOURCE_EXHAUSTED', 'CANCELLED', 'DATA_LOSS', 'UNKNOWN', 'INTERNAL', 'UNIMPLEMENTED', 'UNAVAILABLE', 'DEADLINE_EXCEEDED'])

export class VoiceStudioCloudError extends Error {
    readonly name = 'VoiceStudioCloudError'
    constructor(
        message: string,
        readonly noAudioProduced: boolean,
        readonly httpStatus?: number,
        readonly status?: string,
        readonly reason?: string,
        readonly providerMessage?: string,
        readonly stage: 'synthesis' | 'authentication' | 'connection' = 'synthesis',
    ) { super(message) }
}

function safeCode(value: unknown): string | undefined {
    return typeof value === 'string' && /^[A-Z][A-Z0-9_]{0,79}$/.test(value) ? value : undefined
}

function safeProviderMessage(value: unknown): string | undefined {
    if (typeof value !== 'string') return undefined
    // Keep Google's explanation, never its request config, credentials, or response metadata.
    return value.replace(/-----BEGIN[\s\S]*?-----END[^-]*-----/g, '[redacted]')
        .replace(/\bBearer\s+\S+/gi, 'Bearer [redacted]')
        .replace(/(?:access_token|id_token|refresh_token|client_secret|api[_-]?key|authorization)["']?\s*[=:]\s*["']?[^\s,"'}]+/gi, '[redacted]')
        .replace(/https?:\/\/\S+/gi, '[URL]')
        .replace(/[A-Za-z0-9_+/=-]{32,}/g, '[redacted]')
        .replace(/[\r\n\t]+/g, ' ').trim().slice(0, 240) || undefined
}

function cloudFailure(error: any): { error: VoiceStudioCloudError; retryable: boolean } {
    const response = error?.response
    const httpStatus = Number(response?.status) || undefined
    const data = response?.data
    const detail = data && typeof data === 'object' && data.error && typeof data.error === 'object'
        ? data.error : null
    const status = safeCode(detail?.status)
    const errorInfo = Array.isArray(detail?.details)
        ? detail.details.find((item: any) => item?.['@type'] === 'type.googleapis.com/google.rpc.ErrorInfo') : undefined
    const reason = safeCode(errorInfo?.reason)
    const providerMessage = safeProviderMessage(detail?.message)
    let stage: 'synthesis' | 'authentication' | 'connection' = 'synthesis'
    let googleEndpoint = true
    const requestUrl = response?.config?.url || error?.config?.url
    if (requestUrl) {
        try {
            const host = new URL(String(requestUrl)).hostname
            googleEndpoint = host.endsWith('.googleapis.com') || host.endsWith('.google.com')
            if (host !== 'texttospeech.googleapis.com') stage = googleEndpoint ? 'authentication' : 'connection'
        } catch { googleEndpoint = false; stage = 'connection' }
    }
    const uncertainTimeout = [408, 499, 504].includes(httpStatus || 0) || status === 'DEADLINE_EXCEEDED' || status === 'CANCELLED'
    const explicitRejection = Boolean(!uncertainTimeout && googleEndpoint && httpStatus && httpStatus >= 400 && detail
        && (Number(detail.code) === httpStatus || (status && GOOGLE_STATUSES.has(status))) && !data.audioContent)
    const classification = `${status || ''} ${reason || ''} ${detail?.message || ''}`
    const safety = /safety|prohibited|blocked|harmful|responsible.?ai|content.?policy|sensitive.?content|usage.?guidelines|support\s*codes?:/i.test(classification)
    const billing = /billing|payment/i.test(classification)
    const access = /permission|unauthenticated|api.?key|service.disabled|access.denied|forbidden/i.test(classification)
    const invalid = /invalid.argument|bad.request|failed.precondition|out.of.range/i.test(classification)
    const retryable = explicitRejection && [429, 500, 503].includes(httpStatus!) && !safety && !billing && !access && !invalid
    const source = stage === 'authentication' ? 'Google 인증 서버' : 'Google 음성 서버'
    const guidance = safety ? 'Google이 이 구간의 음성 생성을 거부했습니다. 대본과 말투 지시를 확인해 주세요.'
        : billing ? 'Google Cloud 결제 설정으로 음성을 생성하지 못했습니다. 결제 상태를 확인해 주세요.'
        : access || httpStatus === 401 || httpStatus === 403 ? 'Google Cloud 인증 또는 API 사용 권한을 확인해 주세요.'
        : invalid || httpStatus === 400 ? 'Google 음성 요청이 거부됐습니다. 구간의 대본과 음성 설정을 확인해 주세요.'
        : httpStatus === 429 ? `${source}의 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.`
        : httpStatus && httpStatus >= 500 ? `${source}의 오류로 음성을 받지 못했습니다. 잠시 후 다시 시도해 주세요.`
        : 'Google 음성 요청의 완료 여부를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.'
    const codes = [httpStatus, status, reason].filter(Boolean).join(' / ')
    return { error: new VoiceStudioCloudError(`${guidance}${codes ? ` (${codes})` : ''}${providerMessage ? ` ${providerMessage}` : ''}`,
        explicitRejection, httpStatus, status, reason, providerMessage, stage), retryable }
}

export async function generateVoiceStudioMp3(input: {text: string; voiceId: string; direction?: string; speed?: number; language?: string}) {
    const project = process.env.VOICE_STUDIO_CLOUD_PROJECT || process.env.GOOGLE_CLOUD_PROJECT
    if (!project) throw new Error('Voice Studio 웹 서버의 Google Cloud 프로젝트와 공식 인증을 먼저 설정해 주세요.')
    const voice = voiceStudioName(input.voiceId)
    const text = input.text.trim()
    const direction = input.direction || '자연스럽고 차분하게 원문만 낭독하세요.'
    if (!text || Buffer.byteLength(text, 'utf8') > 3500 || Buffer.byteLength(direction, 'utf8') > 2000) throw new Error('Voice Studio 구간 또는 말투 지시가 너무 깁니다.')
    const speed = Number(input.speed ?? 1)
    if (!Number.isFinite(speed) || speed < .7 || speed > 1.3) throw new Error('음성 속도는 0.7~1.3 사이여야 합니다.')
    const language = input.language || 'ko-KR'
    const body = {input: {text, prompt: `${direction}\nRead at approximately ${speed}x normal speaking pace. Read only the supplied text.`},
        voice: {languageCode: language, name: voice, modelName: 'gemini-2.5-flash-tts'},
        audioConfig: {audioEncoding: 'MP3', sampleRateHertz: 44100}}
    const key = createHash('sha256').update(JSON.stringify([project, body])).digest('hex')
    const existing = pending.get(key)
    if (existing) return existing
    const work = (async () => {
        const dir = join(tmpdir(), 'air-voice-studio-cache')
        const path = join(dir, key + '.mp3')
        try {const cached = await readFile(path); if (cached.length > 256) return cached} catch {}
        const deadline = Date.now() + REQUEST_BUDGET_MS
        const client = await voiceStudioAuth(project)
        let result: { data: { audioContent: string } } | undefined
        let lastFailure: VoiceStudioCloudError | undefined
        for (let attempt = 0; attempt < 3; attempt++) {
            const remaining = deadline - Date.now()
            if (remaining <= 0) throw lastFailure || new VoiceStudioCloudError('Google 음성 요청 시간이 초과됐습니다. 잠시 후 다시 시도해 주세요.', false)
            try {
                result = await client.request<{audioContent: string}>({
                    url: SYNTHESIS_URL, method:'POST',
                    headers: {'x-goog-user-project': project}, data: body, timeout: remaining, retry: false,
                })
                break
            } catch (error) {
                const failure = cloudFailure(error)
                lastFailure = failure.error
                const delay = 1000 * (2 ** attempt)
                if (!failure.retryable || attempt === 2 || deadline - Date.now() <= delay) throw lastFailure
                await new Promise(resolve => setTimeout(resolve, delay))
            }
        }
        if (!result) throw lastFailure || new VoiceStudioCloudError('Google 음성 응답을 확인하지 못했습니다.', false)
        const audio = Buffer.from(typeof result.data?.audioContent === 'string' ? result.data.audioContent : '', 'base64')
        if (audio.length < 256) throw new VoiceStudioCloudError('Google 음성 응답이 비어 있거나 불완전합니다. 잠시 후 다시 시도해 주세요.', false)
        await mkdir(dir, {recursive:true})
        const temp = path + '.' + randomUUID()
        await writeFile(temp, audio)
        await rename(temp, path)
        return audio
    })()
    pending.set(key, work)
    try {return await work} finally {pending.delete(key)}
}
