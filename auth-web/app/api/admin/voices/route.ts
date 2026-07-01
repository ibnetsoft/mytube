import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

type CustomVoice = {
    name: string
    voice_id: string
    provider: 'elevenlabs'
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
            .map(item => ({
                name: String(item?.name || '').trim(),
                voice_id: String(item?.voice_id || '').trim(),
                provider: 'elevenlabs' as const,
            }))
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
        return NextResponse.json({ voices: await loadVoices() })
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
            const existing = voices.find(voice => voice.voice_id === requested.voice_id)
            if (existing) existing.name = requested.name
            else voices.push(requested)
        }
        await saveVoices(voices)
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
        return NextResponse.json({ success: true, voices })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
