import { NextResponse } from 'next/server'
import { randomUUID } from 'crypto'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { validateTopicSubmission } from '@/lib/topicSubmission'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    const { data, error } = await supabaseAdmin.from('user_topic_submissions')
        .select('id,title,status,job_id,review_note,created_at,reviewed_at,request_data')
        .eq('owner_email', auth.requester.email.toLowerCase()).order('created_at', { ascending: false }).limit(100)
    if (error) return NextResponse.json({ error: '토픽 목록을 불러오지 못했습니다.' }, { status: 502 })
    const categories = await supabaseAdmin.from('categories').select('id,name').order('name', { ascending: true })
    if (categories.error) return NextResponse.json({ error: '카테고리 목록을 불러오지 못했습니다.' }, { status: 502 })
    const ids = (data || []).map(row => row.job_id).filter(Boolean)
    const jobs = ids.length ? await supabaseAdmin.from('script_worker_jobs').select('id,status').in('id', ids) : { data: [], error: null }
    return NextResponse.json({ categories: categories.data || [], items: (data || []).map(row => ({
        id: row.id,
        title: row.title,
        status: row.status,
        job_id: row.job_id,
        review_note: row.review_note,
        created_at: row.created_at,
        reviewed_at: row.reviewed_at,
        ae_scene_delivery: row.request_data?.ae_scene_delivery === 'gcs' ? 'gcs' : 'local',
        job_status: jobs.data?.find(job => job.id === row.job_id)?.status || null,
    })) })
}

export async function POST(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    let payload
    try {
        // Bound the actual stream, including chunked requests without Content-Length.
        const reader = req.body?.getReader()
        if (!reader) throw new Error('입력 내용이 없습니다.')
        const chunks: Uint8Array[] = []; let size = 0
        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            size += value.length
            if (size > 2300000) { await reader.cancel(); throw new Error('등록 용량을 초과했습니다.') }
            chunks.push(value)
        }
        payload = validateTopicSubmission(JSON.parse(Buffer.concat(chunks).toString('utf8')))
    } catch (error) {
        return NextResponse.json({ error: error instanceof Error ? error.message : '입력을 확인하세요.' }, { status: 400 })
    }
    const key = req.headers.get('idempotency-key') || ''
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(key)) return NextResponse.json({ error: '등록 ID가 올바르지 않습니다.' }, { status: 400 })
    const owner = auth.requester.email.toLowerCase()
    const { error } = await supabaseAdmin.from('user_topic_submissions').insert({ id: key || randomUUID(), owner_email: owner, title: payload.title, request_data: payload })
    if (error?.code === '23505') {
        const existing = await supabaseAdmin.from('user_topic_submissions').select('id').eq('id', key).eq('owner_email', owner).maybeSingle()
        if (existing.data) return NextResponse.json({ id: key })
    }
    if (error) return NextResponse.json({ error: '토픽 저장에 실패했습니다. 다시 시도하세요.' }, { status: 502 })
    return NextResponse.json({ id: key }, { status: 201 })
}
