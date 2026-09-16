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
    remapSubtitleTranslations,
} from '@/lib/stdSubtitleTranslation'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const MAX_BLOCKS = 500
const MAX_BLOCK_TEXT = 1200
const MAX_TOTAL_TEXT = 120_000
const BATCH_SIZE = 30
const SUBTITLE_TRANSLATION_MODEL_SETTING_KEY = 'sys_api_subtitle_translation_model'
const DEFAULT_SUBTITLE_TRANSLATION_MODEL = 'gpt-5.3-codex-spark'
const SUBTITLE_EDIT_TRANSLATION_MODEL_SETTING_KEY = 'sys_api_subtitle_edit_translation_model'
const DEFAULT_SUBTITLE_EDIT_TRANSLATION_MODEL = 'gemini-3.6-flash'
const SUBTITLE_TRANSLATION_SCOPE_KEY = 'sys_api_subtitle_translation_scope'

async function geminiApiKey(): Promise<string> {
    if (process.env.SUBTITLE_TRANSLATION_GEMINI_API_KEY) return process.env.SUBTITLE_TRANSLATION_GEMINI_API_KEY
    if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY
    const { data } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', 'sys_api_gemini')
        .maybeSingle()
    return String(data?.value || '')
}

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
        return NextResponse.json({ success: false, error: 'English, Vietnamese, or Thai subtitle blocks are required' }, { status: 400 })
    }
    const targetLanguage = body.target_language
    const preferGeminiForSubtitleEdit = body?.prefer_gemini === true
    const translationScope = await subtitleTranslationScope()
    if (translationScope !== 'all' && targetLanguage !== 'th') {
        return NextResponse.json({
            success: false,
            error: 'Subtitle translation is configured for Thai only',
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
    const cached = translationMapFromBlocks(remapSubtitleTranslations(
        Array.isArray(cachedBlocks) ? cachedBlocks : [], blocks,
    ))
    const translated = new Map<string, string>()
    const missing = blocks.filter((block: any) => {
        const cachedText = cached[subtitleTranslationKey(block.index, block.source_text)]
        if (cachedText) translated.set(String(block.index), cachedText)
        return !cachedText
    })

    try {
        if (missing.length > 0) {
            const apiKey = await geminiApiKey()

            for (let offset = 0; offset < missing.length; offset += BATCH_SIZE) {
                const batch = missing.slice(offset, offset + BATCH_SIZE)
                const source = batch.map((block: any) => ({ id: `b${block.index}`, text: block.source_text }))
                const raw = await generateJsonWithModelSetting(
                    supabaseAdmin,
                    buildSubtitleTranslationPrompt(source, targetLanguage),
                    preferGeminiForSubtitleEdit ? SUBTITLE_EDIT_TRANSLATION_MODEL_SETTING_KEY : SUBTITLE_TRANSLATION_MODEL_SETTING_KEY,
                    apiKey,
                    0.1,
                    {
                        defaultModel: preferGeminiForSubtitleEdit ? DEFAULT_SUBTITLE_EDIT_TRANSLATION_MODEL : DEFAULT_SUBTITLE_TRANSLATION_MODEL,
                        disableFallback: !preferGeminiForSubtitleEdit,
                    },
                )
                const result = parseStrictTranslationResponse(raw, source)
                for (const item of result) translated.set(item.id.slice(1), item.translation)
            }
        }
    } catch (error: any) {
        const blocked = String(error?.message || '').includes('API_KEY_SERVICE_BLOCKED')
        console.error('[subtitle-translations] generation failed', { status: error?.status, blocked })
        return NextResponse.json({
            success: false,
            error: blocked
                ? 'Gemini 자막 번역 키의 API 사용 권한이 차단되어 있습니다. 관리자 키 설정을 확인해 주세요.'
                : '자막 번역 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.',
        }, { status: 502 })
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
        model_setting_key: preferGeminiForSubtitleEdit ? SUBTITLE_EDIT_TRANSLATION_MODEL_SETTING_KEY : SUBTITLE_TRANSLATION_MODEL_SETTING_KEY,
        default_model: preferGeminiForSubtitleEdit ? DEFAULT_SUBTITLE_EDIT_TRANSLATION_MODEL : DEFAULT_SUBTITLE_TRANSLATION_MODEL,
        scope: translationScope,
        persisted: !persisted.error,
    })
}
