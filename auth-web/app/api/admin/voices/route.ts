import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../_auth'
import { deleteServerCache, getServerCache, setServerCache } from '@/lib/server-cache'

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

        const response = { voices: await loadVoices() }
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
        const requestedVoices = normalizeVoices(
            Array.isArray(body.voices) ? body.voices : [body]
        )
        if (!requestedVoices.length) {
            return NextResponse.json({ error: '등록할 음성 이름과 ElevenLabs Voice ID가 필요합니다.' }, { status: 400 })
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
        return NextResponse.json({ success: true, registeredCount: requestedVoices.length, voices })
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
