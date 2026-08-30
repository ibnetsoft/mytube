import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

function isUsableSecretValue(value: string): boolean {
    const normalized = String(value || '').trim()
    if (!normalized) return false
    if (/^[•*]+$/.test(normalized)) return false
    if (['undefined', 'null', '(미설정)', '(unset)'].includes(normalized.toLowerCase())) return false
    return true
}

async function getGlobalSetting(key: string): Promise<string> {
    const { data, error } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', key)
        .maybeSingle()
    if (error) throw error
    return String(data?.value || '').trim()
}

function normalizeKeyPool(...values: string[]): string[] {
    const keys: string[] = []
    for (const raw of values) {
        for (const part of String(raw || '').split(/[\s,;\r\n]+/)) {
            const key = part.trim()
            if (isUsableSecretValue(key) && !keys.includes(key)) keys.push(key)
            if (keys.length >= 4) return keys
        }
    }
    return keys
}

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let elevenLabsKey = ''
    let elevenLabsBackupKeys = ''
    try {
        elevenLabsKey = await getGlobalSetting('sys_api_elevenlabs')
    } catch { }
    try {
        elevenLabsBackupKeys = await getGlobalSetting('sys_api_elevenlabs_keys')
    } catch { }
    if (!elevenLabsKey) {
        elevenLabsKey = process.env.ELEVENLABS_API_KEY || ''
    }
    if (!elevenLabsBackupKeys) {
        elevenLabsBackupKeys = process.env.ELEVENLABS_API_KEYS || ''
    }

    const elevenLabsKeys = normalizeKeyPool(elevenLabsKey, elevenLabsBackupKeys)

    if (!elevenLabsKeys.length) {
        return NextResponse.json({ success: false, error: 'ElevenLabs API key not configured' }, { status: 500 })
    }

    return NextResponse.json({
        success: true,
        elevenlabs_key: elevenLabsKeys[0],
        elevenlabs_key_count: elevenLabsKeys.length,
    })
}
