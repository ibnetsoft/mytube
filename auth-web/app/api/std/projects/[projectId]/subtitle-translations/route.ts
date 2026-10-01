import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import {
    isSubtitleTranslationLanguage,
    SubtitleTranslationBlock,
    subtitleTranslationKey,
    translationMapFromBlocks,
    remapSubtitleTranslations,
} from '@/lib/stdSubtitleTranslation'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
export const maxDuration = 30

const MAX_BLOCKS = 500
const MAX_BLOCK_TEXT = 1200
const MAX_TOTAL_TEXT = 120_000
const SUBTITLE_TRANSLATION_SCOPE_KEY = 'sys_api_subtitle_translation_scope'
const JOB_TABLE = 'std_subtitle_translation_jobs'

async function subtitleTranslationScope(): Promise<'thai_only' | 'all'> {
    const { data } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', SUBTITLE_TRANSLATION_SCOPE_KEY)
        .maybeSingle()
    return String(data?.value || '').trim().toLowerCase() === 'all' ? 'all' : 'thai_only'
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let body: any
    try {
        body = await req.json()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 })
    }
    if (!isSubtitleTranslationLanguage(body?.target_language) || !Array.isArray(body?.blocks)) {
        return NextResponse.json({ success: false, error: 'Korean, English, Vietnamese, or Thai subtitle blocks are required' }, { status: 400 })
    }
    const targetLanguage = body.target_language
    const translationScope = await subtitleTranslationScope()
    if (translationScope !== 'all' && targetLanguage !== 'th' && targetLanguage !== 'ko') {
        return NextResponse.json({
            success: false,
            error: 'Subtitle translation is configured for Thai and Korean',
            scope: translationScope,
        }, { status: 403 })
    }

    const blocks = body.blocks.map((block: any) => ({
        index: Number(block?.index),
        source_text: String(block?.source_text || '').trim(),
    }))
    const totalText = blocks.reduce((sum: number, block: any) => sum + block.source_text.length, 0)
    if (
        blocks.length === 0
        || blocks.length > MAX_BLOCKS
        || totalText > MAX_TOTAL_TEXT
        || new Set(blocks.map((block: any) => block.index)).size !== blocks.length
        || blocks.some((block: any) => !Number.isInteger(block.index) || block.index < 0 || !block.source_text || block.source_text.length > MAX_BLOCK_TEXT)
    ) {
        return NextResponse.json({ success: false, error: 'Invalid subtitle block payload' }, { status: 400 })
    }

    const url = new URL(req.url)
    const impersonating = Boolean(req.headers.get('x-impersonate-email') || url.searchParams.get('impersonate') || url.searchParams.get('email'))
    let { data: project, error } = await supabaseAdmin
        .from('std_projects')
        .select('id,employee_email,project_payload')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()
    if (!project && !error && impersonating) {
        const fallback = await supabaseAdmin
            .from('std_projects')
            .select('id,employee_email,project_payload')
            .eq('id', params.projectId)
            .maybeSingle()
        project = fallback.data
        error = fallback.error
    }
    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const requestedIndexes = body.translate_indexes === undefined ? null : body.translate_indexes
    if (requestedIndexes !== null && (!Array.isArray(requestedIndexes)
        || requestedIndexes.some((index: any) => !Number.isInteger(index) || !blocks.some((block: any) => block.index === index)))) {
        return NextResponse.json({ success: false, error: 'Invalid translation indexes' }, { status: 400 })
    }
    const targets = requestedIndexes === null ? null : new Set<number>(requestedIndexes)
    const cachedBlocks = project.project_payload?.subtitle_translations?.[targetLanguage]?.blocks
    const cached = translationMapFromBlocks(remapSubtitleTranslations(
        Array.isArray(cachedBlocks) ? cachedBlocks : [], blocks,
    ))
    const translated = new Map<string, string>()
    const missing = blocks.filter((block: any) => {
        const cachedText = cached[subtitleTranslationKey(block.index, block.source_text)]
        if (cachedText) translated.set(String(block.index), cachedText)
        return !cachedText && (targets === null || targets.has(block.index))
    })

    if (body.job_id) {
        const { data: job, error: jobError } = await supabaseAdmin.from(JOB_TABLE)
            .select('id,status,result_blocks,source_blocks,error')
            .eq('id', body.job_id).eq('project_id', project.id).eq('target_language', targetLanguage).maybeSingle()
        if (jobError) return NextResponse.json({ success: false, error: '번역 작업 조회 실패' }, { status: 500 })
        if (!job || job.source_blocks.some((source: any) => !blocks.some((block: any) => block.index === source.index && block.source_text === source.source_text))) {
            return NextResponse.json({ success: false, error: '번역 원문이 변경되었습니다. 다시 요청해 주세요.' }, { status: 409 })
        }
        if (job.status === 'failed') return NextResponse.json({ success: false, error: job.error }, { status: 502 })
        if (job.status !== 'completed') return NextResponse.json({ success: true, pending: true, job_id: job.id, provider: 'local-codex' }, { status: 202 })
        for (const item of job.result_blocks || []) translated.set(String(item.index), item.translated_text)
    } else if (missing.length > 0) {
        const requestHash = createHash('sha256').update(JSON.stringify(missing)).digest('hex')
        const existing = await supabaseAdmin.from(JOB_TABLE).select('id,status,result_blocks')
            .eq('project_id', project.id).eq('target_language', targetLanguage).eq('request_hash', requestHash).maybeSingle()
        let job = existing.data
        if (existing.error) return NextResponse.json({ success: false, error: '로컬 번역 작업 조회 실패' }, { status: 500 })
        if (!job) {
            const created = await supabaseAdmin.from(JOB_TABLE).upsert({
                project_id: project.id, target_language: targetLanguage, request_hash: requestHash, source_blocks: missing,
                cached_blocks: blocks.flatMap((block: any) => {
                    const text = translated.get(String(block.index))
                    return text ? [{ ...block, translated_text: text }] : []
                }),
            }, { onConflict: 'project_id,target_language,request_hash', ignoreDuplicates: true })
            if (created.error) return NextResponse.json({ success: false, error: '로컬 번역 작업 저장 실패' }, { status: 500 })
            const fetched = await supabaseAdmin.from(JOB_TABLE).select('id,status,result_blocks')
                .eq('project_id', project.id).eq('target_language', targetLanguage).eq('request_hash', requestHash).single()
            job = fetched.data
        } else if (job.status === 'failed') {
            const retried = await supabaseAdmin.from(JOB_TABLE).update({ status: 'queued', error: null, started_at: null,
                created_at: new Date().toISOString(),
                cached_blocks: blocks.flatMap((block: any) => {
                    const text = translated.get(String(block.index))
                    return text ? [{ ...block, translated_text: text }] : []
                }),
            })
                .eq('id', job.id).eq('status', 'failed')
            if (retried.error) return NextResponse.json({ success: false, error: '로컬 번역 재시도 저장 실패' }, { status: 500 })
            job.status = 'queued'
        }
        if (!job) return NextResponse.json({ success: false, error: '로컬 번역 작업을 찾지 못했습니다.' }, { status: 500 })
        if (job.status !== 'completed') return NextResponse.json({ success: true, pending: true, job_id: job.id, provider: 'local-codex' }, { status: 202 })
        for (const item of job.result_blocks || []) translated.set(String(item.index), item.translated_text)
    }
    const result: SubtitleTranslationBlock[] = blocks.map((block: any) => ({
        ...block, translated_text: translated.get(String(block.index)) || '',
    }))
    if (result.some(block => !block.translated_text && (targets === null || targets.has(block.index)))) {
        return NextResponse.json({ success: false, error: 'Some subtitle blocks were not translated' }, { status: 502 })
    }
    return NextResponse.json({ success: true, blocks: result, target_language: targetLanguage,
        translated_count: missing.length, provider: 'local-codex', scope: translationScope, persisted: true })
}
