import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const KEYS = ['gemini', 'youtube', 'elevenlabs', 'topview', 'topview_uid']

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

export async function GET() {
    try {
        const sb = getAdmin()
        const { data } = await sb.from('global_settings').select('key, value').in('key', KEYS.map(k => `sys_api_${k}`))
        const result: Record<string, string> = {}
        for (const row of (data || [])) {
            const k = row.key.replace('sys_api_', '')
            result[k] = row.value || ''
        }
        return NextResponse.json(result)
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const sb = getAdmin()
        for (const k of KEYS) {
            if (body[k] === undefined) continue
            await sb.from('global_settings').upsert({ key: `sys_api_${k}`, value: body[k] }, { onConflict: 'key' })
        }
        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
