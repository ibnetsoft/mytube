import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

const SUBTITLE_TRANSLATION_SCOPE_KEY = 'sys_api_subtitle_translation_scope'
const DEFAULT_SCOPE = 'thai_only'
const DEFAULT_MODEL = 'local-codex'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { data, error } = await supabaseAdmin
        .from('global_settings')
        .select('key,value')
        .in('key', [SUBTITLE_TRANSLATION_SCOPE_KEY])

    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })

    const settings = new Map((data || []).map((row: any) => [String(row.key), String(row.value || '')]))
    const rawScope = settings.get(SUBTITLE_TRANSLATION_SCOPE_KEY)?.trim().toLowerCase()
    return NextResponse.json({
        success: true,
        scope: rawScope === 'all' ? 'all' : DEFAULT_SCOPE,
        model: DEFAULT_MODEL,
    })
}
