import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../_auth'
import { deleteServerCache, getServerCache, setServerCache } from '@/lib/server-cache'
import { getConfiguredElevenLabsKeys } from '@/lib/elevenLabsKeys'

export const dynamic = 'force-dynamic'
const VOICES_CACHE_KEY = 'admin:voices'
const VOICES_CACHE_TTL_SECONDS = 300

type CustomVoice = {
    id: string
    voice_id: string
    name: string
    gender?: 'male' | 'female'
    category?: string
    language?: string
    description?: string
    preview_url?: string
    provider: 'elevenlabs'
    created_at?: string
}

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

const normalizeVoices = (value: unknown): CustomVoice[] => {
    try {
        const parsed = typeof value === 'string' ? JSON.parse(value) : value
        if (!Array.isArray(parsed)) return []
        return parsed
            .map((item: any) => {
                const vid = String(item?.voice_id || item?.id || '').trim()
                const name = String(item?.name || '').trim()
                const gender = item?.gender === 'male' ? 'male' : 'female'
                return {
                    id: vid,
                    voice_id: vid,
                    name,
                    gender,
                    category: String(item?.category || 'custom').trim(),
                    language: String(item?.language || 'ko').trim(),
                    description: String(item?.description || '').trim(),
                    preview_url: String(item?.preview_url || '').trim(),
                    provider: 'elevenlabs' as const,
                    created_at: item?.created_at || new Date().toISOString(),
                }
            })
            .filter(item => item.name && item.voice_id)
    } catch {
        return []
    }
}

const loadVoices = async () => {
    const sb = getAdmin()
    const { data, error } = await sb
        .from('global_settings')
        .select('value')
        .eq('key', 'custom_voices')
        .maybeSingle()
    if (error) throw error
    return normalizeVoices(data?.value)
}

const saveVoices = async (voices: CustomVoice[]) => {
    const sb = getAdmin()
    const { error } = await sb.from('global_settings').upsert(
        { key: 'custom_voices', value: JSON.stringify(voices) },
        { onConflict: 'key' }
    )
    if (error) throw error
}

const isGenericVoiceName = (value: string) => /^ElevenLabs Voice \d+$/i.test(String(value || '').trim())

async function loadElevenLabsVoiceMetadata() {
    const metadata = new Map<string, Partial<CustomVoice>>()
    const keys = await getConfiguredElevenLabsKeys()
    for (const apiKey of keys) {
        try {
            const res = await fetch('https://api.elevenlabs.io/v1/voices?show_legacy=true', {
                headers: { 'xi-api-key': apiKey },
                cache: 'no-store',
            })
            if (!res.ok) continue
            const data = await res.json().catch(() => ({}))
            for (const voice of data.voices || []) {
                const voiceId = String(voice?.voice_id || '').trim()
                if (!voiceId || metadata.has(voiceId)) continue
                const labels = voice.labels || {}
                const name = String(voice.name || '').trim()
                const lowerName = name.toLowerCase()
                const gender = labels.gender === 'male'
                    ? 'male'
                    : (labels.gender === 'female'
                        ? 'female'
                        : (['mina', 'sian', 'yooni', 'sarah', 'bella', 'alice', 'lily', 'laura', 'jessica', 'selly', 'saori'].some(token => lowerName.includes(token)) ? 'female' : 'male'))
                metadata.set(voiceId, {
                    id: voiceId,
                    voice_id: voiceId,
                    name,
                    gender,
                    category: String(voice.category || 'custom').trim(),
                    language: String(labels.language || 'ko').trim(),
                    description: String(labels.description || voice.description || '').trim(),
                    preview_url: String(voice.preview_url || '').trim(),
                    provider: 'elevenlabs',
                })
            }
        } catch (error) {
            console.warn('Failed to load ElevenLabs voice metadata:', error)
        }
    }
    return metadata
}

async function enrichVoicesWithElevenLabsMetadata(voices: CustomVoice[], existingMetadata?: Map<string, Partial<CustomVoice>>) {
    const metadata = existingMetadata || await loadElevenLabsVoiceMetadata()
    if (!metadata.size) return voices
    return voices.map((voice) => {
        const enriched = metadata.get(voice.voice_id)
        if (!enriched) return voice
        return {
            ...voice,
            ...enriched,
            name: !voice.name || isGenericVoiceName(voice.name)
                ? String(enriched.name || voice.name || voice.voice_id)
                : voice.name,
            description: voice.description || String(enriched.description || ''),
            preview_url: voice.preview_url || String(enriched.preview_url || ''),
            created_at: voice.created_at,
        }
    })
}

export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester
        const cached = await getServerCache<{ voices: CustomVoice[] }>(VOICES_CACHE_KEY)
        if (cached) {
            return NextResponse.json(cached, {
                headers: {
                    'Cache-Control': `private, max-age=${VOICES_CACHE_TTL_SECONDS}`,
                    'X-Admin-Cache': 'HIT',
                },
            })
        }

        const response = { voices: await enrichVoicesWithElevenLabsMetadata(await loadVoices()) }
        await setServerCache(VOICES_CACHE_KEY, response, VOICES_CACHE_TTL_SECONDS)
        return NextResponse.json(response, {
            headers: {
                'Cache-Control': `private, max-age=${VOICES_CACHE_TTL_SECONDS}`,
                'X-Admin-Cache': 'MISS',
            },
        })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const metadata = await loadElevenLabsVoiceMetadata()
        const normalizedVoices = normalizeVoices(
            Array.isArray(body.voices) ? body.voices : [body]
        )
        const unresolvedVoices = normalizedVoices.filter(voice => !metadata.has(voice.voice_id))
        const requestedVoices = await enrichVoicesWithElevenLabsMetadata(
            normalizedVoices.filter(voice => metadata.has(voice.voice_id)),
            metadata
        )
        if (!requestedVoices.length) {
            const suffix = unresolvedVoices.length
                ? ` 현재 저장된 ElevenLabs API 키로 조회 가능한 Voice ID가 없습니다. (${unresolvedVoices.length}개 제외)`
                : ''
            return NextResponse.json({ error: `등록할 음성 이름과 ElevenLabs Voice ID가 필요합니다.${suffix}` }, { status: 400 })
        }

        const voices = await loadVoices()
        for (const requested of requestedVoices) {
            const existingIdx = voices.findIndex(voice => voice.voice_id === requested.voice_id)
            if (existingIdx >= 0) {
                voices[existingIdx] = { ...voices[existingIdx], ...requested }
            } else {
                voices.unshift(requested)
            }
        }
        await saveVoices(voices)
        await deleteServerCache(VOICES_CACHE_KEY)
        return NextResponse.json({
            success: true,
            registeredCount: requestedVoices.length,
            rejectedCount: unresolvedVoices.length,
            rejectedVoiceIds: unresolvedVoices.map(voice => voice.voice_id),
            voices,
        })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function DELETE(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const voiceId = new URL(req.url).searchParams.get('voice_id')?.trim()
        if (!voiceId) {
            return NextResponse.json({ error: 'voice_id가 필요합니다.' }, { status: 400 })
        }

        const voices = (await loadVoices()).filter(voice => voice.voice_id !== voiceId)
        await saveVoices(voices)
        await deleteServerCache(VOICES_CACHE_KEY)
        return NextResponse.json({ success: true, voices })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
