import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

const MUSIC_TASK_FIELDS = `
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
    created_at
`

function isUnavailableMusicMissionSchema(error: any) {
    const code = String(error?.code || '')
    const message = String(error?.message || '')
    return ['42P01', 'PGRST200', 'PGRST205'].includes(code)
        || /music_prompt_tasks|music_submissions|relationship/i.test(message)
}

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
        .select(MUSIC_TASK_FIELDS)
        .order('created_at', { ascending: false })
        .limit(limit)

    if (!includeClosed) query = query.eq('status', 'open')

    const { data, error } = await query
    if (error) {
        if (isUnavailableMusicMissionSchema(error)) {
            return NextResponse.json({ success: true, tasks: [] })
        }
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }

    const email = auth.requester.email.toLowerCase()
    const taskIds = (data || []).map((task: any) => task.id).filter(Boolean)
    let submissions: any[] = []
    if (taskIds.length) {
        const { data: submissionData, error: submissionError } = await supabaseAdmin
            .from('music_submissions')
            .select('id,task_id,submitted_email,file_name,tool_name,status,reward_usdt,review_note,submitted_at')
            .in('task_id', taskIds)

        if (!submissionError) {
            submissions = submissionData || []
        }
    }

    const tasks = (data || []).map((task: any) => ({
        ...task,
        my_submissions: submissions.filter((item: any) =>
            String(item.task_id || '') === String(task.id)
            && String(item.submitted_email || '').toLowerCase() === email
        ),
    }))

    return NextResponse.json({ success: true, tasks })
}
