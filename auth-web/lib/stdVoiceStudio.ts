// Server-only Google Cloud TTS adapter. Never send ADC or project credentials to clients.
import { voiceStudioAuth } from './voiceStudioAuth'
import { createHash, randomUUID } from 'crypto'
import { mkdir, readFile, writeFile, rename } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { voiceStudioName } from './voiceStudioCatalog'

const pending = new Map<string, Promise<Buffer>>()
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
        const client = await voiceStudioAuth(project)
        const result = await client.request<{audioContent: string}>({
            url: 'https://texttospeech.googleapis.com/v1/text:synthesize', method:'POST',
            headers: {'x-goog-user-project': project}, data: body, timeout: 180000, retry: false,
        }).catch((error: any) => {throw new Error(`Voice Studio Cloud 호출 실패 (${error?.response?.status || '인증/연결'}). Cloud Text-to-Speech API, 서버 인증과 결제 프로젝트를 확인해 주세요.`)})
        const audio = Buffer.from(result.data.audioContent || '', 'base64')
        if (audio.length < 256) throw new Error('Voice Studio 음성 응답이 비어 있습니다.')
        await mkdir(dir, {recursive:true})
        const temp = path + '.' + randomUUID()
        await writeFile(temp, audio)
        await rename(temp, path)
        return audio
    })()
    pending.set(key, work)
    try {return await work} finally {pending.delete(key)}
}
