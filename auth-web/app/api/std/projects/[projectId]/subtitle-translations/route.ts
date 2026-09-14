import { NextResponse } from 'next/server'
import { generateJsonWithModelSetting } from '@/lib/aiRouter'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import {
    buildSubtitleTranslationPrompt,
    isSubtitleTranslationLanguage,
    parseStrictTranslationResponse,
    SubtitleTranslationBlock,
    subtitleTranslationKey,
    translationMapFromBlocks,
} from '@/lib/stdSubtitleTranslation'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const MAX_BLOCKS = 500
const MAX_BLOCK_TEXT = 1200
const MAX_TOTAL_TEXT = 120_000
const BATCH_SIZE = 30

async function geminiApiKey(): Promise<string> {
    if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY
    const { data } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', 'sys_api_gemini')
        .maybeSingle()
    return String(data?.value || '')
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
        return NextResponse.json({ success: false, error: 'English, Vietnamese, or Thai subtitle blocks are required' }, { status: 400 })
    }
    const targetLanguage = body.target_language

    const blocks = body.blocks.map((block: any) => ({
        index: Number(block?.index),
        source_text: String(block?.source_text || '').trim(),
    }))
    const totalText = blocks.reduce((sum: number, block: any) => sum + block.source_text.length, 0)
    if (
        blocks.length === 0
        || blocks.length > MAX_BLOCKS
        || totalText > MAX_TOTAL_TEXT
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

    const cachedBlocks = project.project_payload?.subtitle_translations?.[targetLanguage]?.blocks
    const cached = translationMapFromBlocks(cachedBlocks)
    const translated = new Map<string, string>()
    const missing = blocks.filter((block: any) => {
        const cachedText = cached[subtitleTranslationKey(block.index, block.source_text)]
        if (cachedText) translated.set(String(block.index), cachedText)
        return !cachedText
    })

    if (missing.length > 0) {
        const apiKey = await geminiApiKey()
        if (!apiKey) return NextResponse.json({ success: false, error: 'Translation API key is not configured' }, { status: 503 })

        for (let offset = 0; offset < missing.length; offset += BATCH_SIZE) {
            const batch = missing.slice(offset, offset + BATCH_SIZE)
            const source = batch.map((block: any) => ({ id: `b${block.index}`, text: block.source_text }))
            const raw = await generateJsonWithModelSetting(
                supabaseAdmin,
                buildSubtitleTranslationPrompt(source, targetLanguage),
                'sys_api_translation_model',
                apiKey,
                0.1,
            )
            const result = parseStrictTranslationResponse(raw, source)
            for (const item of result) translated.set(item.id.slice(1), item.translation)
        }
    }

    const result: SubtitleTranslationBlock[] = blocks.map((block: any) => ({
        index: block.index,
        source_text: block.source_text,
        translated_text: translated.get(String(block.index)) || '',
    }))
    if (result.some(block => !block.translated_text)) {
        return NextResponse.json({ success: false, error: 'Some subtitle blocks were not translated' }, { status: 502 })
    }

    const latest = await supabaseAdmin.from('std_projects').select('project_payload').eq('id', project.id).single()
    const latestPayload = latest.data?.project_payload || project.project_payload || {}
    const nextTranslations = {
        ...(latestPayload.subtitle_translations || {}),
        [targetLanguage]: { version: 1, updated_at: new Date().toISOString(), blocks: result },
    }
    const persisted = await supabaseAdmin
        .from('std_projects')
        .update({ project_payload: { ...latestPayload, subtitle_translations: nextTranslations } })
        .eq('id', project.id)

    return NextResponse.json({
        success: true,
        target_language: targetLanguage,
        blocks: result,
        cached_count: blocks.length - missing.length,
        translated_count: missing.length,
        persisted: !persisted.error,
    })
}
