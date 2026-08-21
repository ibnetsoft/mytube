import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

async function getGlobalSetting(key: string): Promise<string> {
    const { data, error } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', key)
        .maybeSingle()
    if (error) throw error
    return String(data?.value || '').trim()
}

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let elevenLabsKey = ''
    try {
        elevenLabsKey = await getGlobalSetting('sys_api_elevenlabs')
    } catch { }
    if (!elevenLabsKey) {
        elevenLabsKey = process.env.ELEVENLABS_API_KEY || ''
    }

    if (!elevenLabsKey) {
        return NextResponse.json({ success: false, error: 'ElevenLabs API key not configured' }, { status: 500 })
    }

    return NextResponse.json({
        success: true,
        elevenlabs_key: elevenLabsKey,
    })
}
