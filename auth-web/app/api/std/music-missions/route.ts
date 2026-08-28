import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

function toPositiveInt(value: string | null, fallback: number, max: number) {
    const parsed = Number.parseInt(String(value || ''), 10)
    if (!Number.isFinite(parsed)) return fallback
    return Math.max(1, Math.min(max, parsed))
}

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { searchParams } = new URL(req.url)
    const limit = toPositiveInt(searchParams.get('limit'), 30, 100)
    const includeClosed = ['1', 'true', 'yes'].includes(String(searchParams.get('include_closed') || '').toLowerCase())

    let query = supabaseAdmin
        .from('music_prompt_tasks')
        .select(`
            id,
            title,
            target_market,
            genre,
            mood,
            prompt,
            negative_rules,
            duration_target_seconds,
            reward_usdt,
            max_submissions,
            accepted_submissions_count,
            status,
            metadata,
            created_at,
            music_submissions(
                id,
                submitted_email,
                file_name,
                tool_name,
                status,
                reward_usdt,
                review_note,
                submitted_at
            )
        `)
        .order('created_at', { ascending: false })
        .limit(limit)

    if (!includeClosed) query = query.eq('status', 'open')

    const { data, error } = await query
    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })

    const email = auth.requester.email.toLowerCase()
    const tasks = (data || []).map((task: any) => ({
        ...task,
        my_submissions: Array.isArray(task.music_submissions)
            ? task.music_submissions.filter((item: any) => String(item.submitted_email || '').toLowerCase() === email)
            : [],
        music_submissions: undefined,
    }))

    return NextResponse.json({ success: true, tasks })
}
