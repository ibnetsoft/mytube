import { generateJsonWithModelSetting } from '../../../../lib/aiRouter'

// AIR-0229: 공지사항 게시판(PR #104)에 다국어 자동번역을 얹는 헬퍼.
// 한글 원문(title/body)을 en/vi/th로 번역해 title_*/body_* 컬럼에 저장한다.
// 언어별로 개별 try/catch — 한 언어가 실패해도 나머지는 저장되도록
// topics-queue의 translateAndSaveTopics와 동일한 방식.

const LANG_MAP = [
    { code: 'en', name: 'English' },
    { code: 'vi', name: 'Vietnamese' },
    { code: 'th', name: 'Thai' },
] as const

function buildTranslationPrompt(titleKo: string, bodyKo: string, langName: string): string {
    return `You are a professional ${langName} translator for a video-production SaaS platform's admin announcement.
Translate the following Korean announcement to natural, fluent ${langName}.
Preserve line breaks in the body. Return ONLY valid JSON, no markdown, no explanation.

Title (Korean): ${titleKo}
Body (Korean):
${bodyKo}

Return format:
{"title":"<translated title>","body":"<translated body>"}`
}

function parseTranslationResponse(raw: string): { title: string; body: string } | null {
    try {
        const parsed = JSON.parse(raw)
        const title = String(parsed?.title ?? '').trim()
        const body = String(parsed?.body ?? '').trim()
        if (!title && !body) return null
        return { title, body }
    } catch {
        return null
    }
}

async function resolveGeminiApiKey(supabase: any): Promise<string> {
    let geminiApiKey = process.env.GEMINI_API_KEY
    if (!geminiApiKey) {
        const { data } = await supabase
            .from('global_settings')
            .select('value')
            .eq('key', 'sys_api_gemini')
            .maybeSingle()
        geminiApiKey = data?.value
    }
    return geminiApiKey || ''
}

// 텍스트가 짧아(제목+본문) 동기 처리해도 admin 저장 액션이 오래 걸리지 않는다.
export async function translateAndSaveAnnouncement(
    id: string,
    titleKo: string,
    bodyKo: string,
    supabase: any
): Promise<void> {
    const geminiApiKey = await resolveGeminiApiKey(supabase)
    if (!geminiApiKey) {
        await supabase.from('announcements').update({ translation_status: 'failed' }).eq('id', id)
        return
    }

    await supabase.from('announcements').update({ translation_status: 'running' }).eq('id', id)

    const columns: Record<string, string> = {}
    for (const lang of LANG_MAP) {
        try {
            const prompt = buildTranslationPrompt(titleKo, bodyKo, lang.name)
            const text = await generateJsonWithModelSetting(supabase, prompt, 'sys_api_translation_model', geminiApiKey)
            const parsed = parseTranslationResponse(text)
            if (parsed) {
                columns[`title_${lang.code}`] = parsed.title
                columns[`body_${lang.code}`] = parsed.body
            }
        } catch (err) {
            console.error(`[Announcements] translation failed for lang=${lang.code}`, err)
        }
    }

    await supabase.from('announcements').update({
        ...columns,
        translation_status: Object.keys(columns).length ? 'completed' : 'failed',
    }).eq('id', id)
}
