import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { GoogleGenAI } from '@google/genai'
import { isAuthResponse, requireAdmin, requireSuperAdmin } from '../_auth'
import { generateJsonWithModelSetting } from '../../../../lib/aiRouter'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function toInt(value: any, fallback: number) {
    const parsed = Number.parseInt(String(value ?? ''), 10)
    return Number.isFinite(parsed) ? parsed : fallback
}

// 앱이 지원하는 스타일 키 목록 (로컬 SQLite style_presets/script_style_presets와 동기화).
// Next.js 라우트는 Supabase만 접근하므로 로컬 DB를 직접 읽을 수 없어 여기에 하드코딩한다.
// script_plan.html / image_gen.html 의 스타일 옵션이 바뀌면 이 목록도 함께 갱신해야 한다.
const SCRIPT_STYLE_KEYS = [
    'default', 'news', 'story', 'senior_story', 'bgm',
    'classic_50s', 'joseon_sageuk', 'north_korean_drama', 'silent_20s', 'camcorder_90s', 'modern_drama',
    'mystery_thriller', 'horror_suspense', 'melodrama', 'crime_drama', 'cyberpunk_neon',
    'k_manhwa', 'watercolor_analog', 'k_webtoon', 'graphite_sketch', 'joseon_2d_anime',
    'oriental_ink', 'neonsign_citypop', 'buddhist_minimal', 'renaissance_sacred', 'cute_animal_char',
    'nursery_rhyme'
]

const IMAGE_STYLE_KEYS = [
    'realistic', 'anime', 'cinematic', 'cartoon', 'oil_painting', 'watercolor', 'sketch',
    'pixel_art', '3d', 'k_webtoon', 'ghibli', 'k_manhwa', 'minimal', 'nursery_rhyme'
]

const DEFAULT_SCRIPT_STYLE = 'default'
const DEFAULT_IMAGE_STYLE = 'realistic'
const CONTENT_LANGUAGES = ['ko', 'en', 'ja'] as const

type ContentLanguage = typeof CONTENT_LANGUAGES[number]

function normalizeContentLanguage(value: any): ContentLanguage {
    const lang = String(value || '').trim().toLowerCase()
    return CONTENT_LANGUAGES.includes(lang as ContentLanguage) ? lang as ContentLanguage : 'ko'
}

function contentLanguageLabel(value: any): string {
    const lang = normalizeContentLanguage(value)
    return lang === 'en' ? 'English' : lang === 'ja' ? '日本語' : '한국어'
}

function topicLanguageInstruction(targetLang: ContentLanguage): string {
    if (targetLang === 'en') {
        return `
        LANGUAGE REQUIREMENTS:
        - All output fields, especially "topic" and "duration_reason", MUST be written in natural, fluent English.
        - Do not mix Korean or Japanese into the topic title unless it is a proper noun that must remain untranslated.
        - Title examples: "The Untold Mystery of the Joseon Dynasty", "5 Life-Changing Money Habits of Self-Made Millionaires".
        `
    }
    if (targetLang === 'ja') {
        return `
        LANGUAGE REQUIREMENTS:
        - All output fields, especially "topic" and "duration_reason", MUST be written in natural Japanese.
        - Use polished Japanese phrasing suitable for YouTube titles; avoid Korean sentence fragments.
        - Title examples: "日本史を揺るがした本能寺の変の真実", "50代から始める、後悔しない人生設計のコツ".
        `
    }
    return `
        LANGUAGE REQUIREMENTS:
        - 모든 출력 필드, 특히 "topic"과 "duration_reason"은 자연스럽고 흥미로운 한국어로 작성되어야 합니다.
        - 예시: "조선 왕조를 뒤흔든 숨겨진 비화", "평생 고생한 자식에게 전하는 눈물 나는 인생 조언".
        `
}

function isMissingColumnError(err: any): boolean {
    if (!err) return false
    const code = String(err.code || '')
    if (code === 'PGRST204' || code === '42703') return true
    const msg = String(err.message || '').toLowerCase()
    return (
        msg.includes('schema cache') ||
        /could not find the .* column/.test(msg) ||
        /column .* does not exist/.test(msg)
    )
}

// --- AIR-0129: Admin auto-translation pipeline ---

type TranslationTopic = { id: string; topic: string; category_name: string }

function buildTranslationPrompt(topics: TranslationTopic[], langCode: string, langName: string): string {
    const itemLines = topics.map(t =>
        JSON.stringify({ id: t.id, topic: t.topic, category_name: t.category_name })
    ).join('\n')
    return `You are a professional ${langName} translator for YouTube content.
Translate the topic titles and category names to natural, fluent ${langName}.
Topic titles must work as compelling YouTube video titles in ${langName}.
Return ONLY valid JSON array. No markdown, no explanation.

Input topics (JSON objects):
${itemLines}

Return format:
[
  {"id":"<same id>","topic_${langCode}":"<translated topic>","category_name_${langCode}":"<translated category name>"}
]`
}

function parseTranslationResponse(
    raw: string,
    validIds: Set<string>,
    langCode: string
): Record<string, { topic: string; category_name: string }> {
    try {
        const parsed = JSON.parse(raw)
        if (!Array.isArray(parsed)) return {}
        const result: Record<string, { topic: string; category_name: string }> = {}
        for (const item of parsed) {
            const id = String(item?.id ?? '').trim()
            if (!id || !validIds.has(id)) continue
            const topic = String(item?.[`topic_${langCode}`] ?? '').trim()
            const catName = String(item?.[`category_name_${langCode}`] ?? '').trim()
            if (topic) result[id] = { topic, category_name: catName }
        }
        return result
    } catch {
        return {}
    }
}

async function translateAndSaveTopics(
    topicIds: string[],
    supabase: ReturnType<typeof getAdmin>,
    geminiApiKey: string
): Promise<void> {
    if (!topicIds.length || !geminiApiKey) return
    try {
        // Mark as running before starting AI calls
        await supabase
            .from('topics_queue')
            .update({ translation_status: 'running' })
            .in('id', topicIds)

        // Fetch topic text and category names for all target IDs
        const { data: rows, error: fetchError } = await supabase
            .from('topics_queue')
            .select('id, topic, categories(name)')
            .in('id', topicIds)

        if (fetchError || !rows?.length) {
            await supabase
                .from('topics_queue')
                .update({ translation_status: 'failed' })
                .in('id', topicIds)
            return
        }

        const topics: TranslationTopic[] = rows.map((r: any) => ({
            id: String(r.id),
            topic: String(r.topic || ''),
            category_name: String(r.categories?.name || ''),
        }))
        const validIds = new Set(topics.map(t => t.id))

        const LANG_MAP = [
            { code: 'vi', name: 'Vietnamese' },
            { code: 'en', name: 'English' },
            { code: 'th', name: 'Thai' },
        ] as const

        // Accumulate translations per topic ID across all languages
        const allTranslations: Record<string, Record<string, string>> = {}
        for (const t of topics) allTranslations[t.id] = {}

        for (const lang of LANG_MAP) {
            try {
                const prompt = buildTranslationPrompt(topics, lang.code, lang.name)
                // AIR-0225: respects the "번역 모델" admin setting instead of
                // always using Gemini.
                const text = await generateJsonWithModelSetting(
                    supabase,
                    prompt,
                    'sys_api_translation_model',
                    geminiApiKey
                )
                const parsed = parseTranslationResponse(text, validIds, lang.code)
                for (const [id, val] of Object.entries(parsed)) {
                    allTranslations[id][`topic_${lang.code}`] = val.topic
                    allTranslations[id][`category_name_${lang.code}`] = val.category_name
                }
            } catch (langErr) {
                console.error(`AIR-0129: translation failed for lang=${lang.code}`, langErr)
                // Continue with remaining languages — partial save is acceptable
            }
        }

        // Persist all available columns for each topic that has at least one translation
        const now = new Date().toISOString()
        await Promise.all(
            topics.map(async (t) => {
                const cols = allTranslations[t.id]
                if (!Object.keys(cols).length) return
                const { error: saveError } = await supabase
                    .from('topics_queue')
                    .update({ ...cols, translated_at: now, translation_status: 'completed' })
                    .eq('id', t.id)
                if (saveError && !isMissingColumnError(saveError)) {
                    console.error(`AIR-0129: save failed for topic id=${t.id}`, saveError)
                }
            })
        )

        // Mark any topics with zero translations as failed
        const failedIds = topics
            .filter(t => !Object.keys(allTranslations[t.id]).length)
            .map(t => t.id)
        if (failedIds.length) {
            await supabase
                .from('topics_queue')
                .update({ translation_status: 'failed' })
                .in('id', failedIds)
        }
    } catch (err) {
        console.error('AIR-0129: translateAndSaveTopics failed', err)
        try {
            await supabase
                .from('topics_queue')
                .update({ translation_status: 'failed' })
                .in('id', topicIds)
        } catch {}
    }
}

function pickValidStyle(value: any, allowed: string[], fallback: string): string {
    const key = String(value ?? '').trim()
    return allowed.includes(key) ? key : fallback
}

function clampDuration(value: any, minMinutes: number) {
    const parsed = toInt(value, minMinutes)
    return Math.max(minMinutes, Math.min(60, parsed))
}

function payoutForMinutes(minutes: number, minMinutes: number, basePay: number, extraPerMinute: number) {
    return basePay + Math.max(0, minutes - minMinutes) * extraPerMinute
}

function toStringArray(value: any): string[] {
    if (Array.isArray(value)) {
        return value.map((item) => String(item ?? '').trim()).filter(Boolean)
    }
    if (typeof value === 'string') {
        const trimmed = value.trim()
        if (!trimmed) return []
        try {
            const parsed = JSON.parse(trimmed)
            if (Array.isArray(parsed)) {
                return parsed.map((item) => String(item ?? '').trim()).filter(Boolean)
            }
        } catch {}
        return trimmed.split(',').map((item) => item.trim()).filter(Boolean)
    }
    return []
}

function durationPreferenceBucket(minutes: number | null) {
    if (!minutes || minutes <= 0) return ''
    if (minutes <= 15) return '15m'
    if (minutes <= 30) return '30m'
    return '60m_plus'
}

// 유저의 preferred_video_length 버킷에 맞게 duration을 보정
function adjustToBucket(duration: number, bucket: string, minMinutes: number): number {
    if (!bucket) return duration
    if (bucket === '15m') return Math.max(minMinutes, Math.min(15, duration))
    if (bucket === '30m') return Math.max(minMinutes, Math.min(30, duration))
    if (bucket === '60m_plus') return Math.max(Math.max(minMinutes, 30), Math.min(60, duration))
    return duration
}

type PreferredWorker = {
    email: string
    preferredCategoryIds: string[]
    preferredVideoLength: string
    preferredLanguages: ContentLanguage[]
    activeLoad: number
}

async function loadPreferredWorkers(supabase: ReturnType<typeof getAdmin>): Promise<PreferredWorker[]> {
    let profiles: any[] | null = null
    let profilesError: any = null
    const initial = await supabase
        .from('profiles')
        .select('email,is_approved,preferred_category_ids,preferred_video_length,preferred_languages')
    profiles = initial.data as any[] | null
    profilesError = initial.error

    if (isMissingColumnError(profilesError)) {
        const retry = await supabase
            .from('profiles')
            .select('email,is_approved,preferred_category_ids,preferred_video_length')
        profiles = retry.data as any[] | null
        profilesError = retry.error
    }

    if (profilesError) throw profilesError

    const { data: queueRows, error: queueError } = await supabase
        .from('topics_queue')
        .select('assigned_employee_email,status')
        .in('status', ['pending', 'assigned'])

    if (queueError) throw queueError

    const loadMap = new Map<string, number>()
    for (const row of queueRows || []) {
        const email = String(row.assigned_employee_email || '').trim().toLowerCase()
        if (!email) continue
        loadMap.set(email, (loadMap.get(email) || 0) + 1)
    }

    return (profiles || [])
        .filter((profile: any) => profile?.email && profile?.is_approved === true)
        .map((profile: any) => {
            const email = String(profile.email || '').trim().toLowerCase()
            const rawLanguages = Array.isArray(profile.preferred_languages)
                ? profile.preferred_languages
                : toStringArray(profile.preferred_languages)
            const preferredLanguages = rawLanguages
                .map(normalizeContentLanguage)
                .filter((lang: ContentLanguage, index: number, arr: ContentLanguage[]) => arr.indexOf(lang) === index)
            return {
                email,
                preferredCategoryIds: toStringArray(profile.preferred_category_ids),
                preferredVideoLength: String(profile.preferred_video_length || '').trim(),
                preferredLanguages: preferredLanguages.length ? preferredLanguages : ['ko'],
                activeLoad: loadMap.get(email) || 0,
            }
        })
}

function pickPreferredWorker(
    workers: PreferredWorker[],
    fallbackEmail: string,
    categoryId: any,
    durationMinutes: number | null,
    isLongformCategory: boolean,
    targetLanguage: ContentLanguage = 'ko'
): PreferredWorker | null {
    const fallback = String(fallbackEmail || '').trim().toLowerCase()
    const targetCategoryId = String(categoryId ?? '').trim()
    const targetBucket = isLongformCategory ? durationPreferenceBucket(durationMinutes) : ''
    const languageMatchedWorkers = workers.filter((worker) => worker.preferredLanguages.includes(targetLanguage))

    // 언어 지원자가 없으면 오배정을 막기 위해 미배정 상태로 둔다.
    if (!languageMatchedWorkers.length) return null

    const designated = fallback ? languageMatchedWorkers.find((worker) => worker.email === fallback) : null
    if (designated) return designated

    const categoryMatched = targetCategoryId
        ? languageMatchedWorkers.filter((worker) => worker.preferredCategoryIds.includes(targetCategoryId))
        : []
    const candidates = categoryMatched.length ? categoryMatched : languageMatchedWorkers

    const ranked = [...candidates].sort((a, b) => {
        const aDurationRank = !isLongformCategory
            ? 0
            : a.preferredVideoLength === targetBucket
            ? 0
            : !a.preferredVideoLength
            ? 1
            : 2
        const bDurationRank = !isLongformCategory
            ? 0
            : b.preferredVideoLength === targetBucket
            ? 0
            : !b.preferredVideoLength
            ? 1
            : 2
        if (aDurationRank !== bDurationRank) return aDurationRank - bDurationRank
        if (a.activeLoad !== b.activeLoad) return a.activeLoad - b.activeLoad
        if (a.email === fallback) return -1
        if (b.email === fallback) return 1
        return a.email.localeCompare(b.email)
    })

    return ranked[0] || null
}

function normalizeTopicQueueRow(topic: any) {
    const assetMix = topic?.asset_mix_summary && typeof topic.asset_mix_summary === 'object'
        ? topic.asset_mix_summary
        : {}
    const totalScenes = toInt(topic?.total_scenes ?? assetMix?.total_scenes, 0)
    const videoScenes = toInt(topic?.video_scenes ?? assetMix?.video_scenes, 0)
    const imageScenes = toInt(topic?.image_scenes ?? assetMix?.image_scenes, 0)
    const actualPayout = toInt(topic?.actual_payout ?? assetMix?.actual_payout, 0)
    const fallbackRatio = totalScenes > 0 ? `${videoScenes}/${totalScenes}` : null
    const videoClipRatio = String(topic?.video_clip_ratio || assetMix?.video_clip_ratio || fallbackRatio || '').trim()

    const language = normalizeContentLanguage(topic?.language || topic?.categories?.language)
    return {
        ...topic,
        language,
        language_label: contentLanguageLabel(language),
        total_scenes: totalScenes,
        video_scenes: videoScenes,
        image_scenes: imageScenes,
        actual_payout: actualPayout,
        video_clip_ratio: videoClipRatio,
    }
}

// GET: 대기열 주제 목록 조회
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const email = searchParams.get('email')
        const status = searchParams.get('status') || 'active'

        const supabase = getAdmin()
        let query = supabase
            .from('topics_queue')
            .select('*, categories(*)')
            .order('created_at', { ascending: false })

        if (status === 'active') {
            query = query.in('status', ['pending', 'assigned'])
        } else if (status && status !== 'all') {
            // Non-active statuses (e.g. 'completed') accumulate forever, unlike
            // the always-small pending/assigned queue - cap it so this doesn't
            // grow into an unbounded payload as history piles up.
            query = query.eq('status', status).limit(1000)
        }

        const { data, error } = await query

        if (error) throw error

        let topics = (data || []).map((topic: any) => normalizeTopicQueueRow(topic))

        if (email) {
            topics = topics.filter((topic: any) => topic.assigned_employee_email === email)
        }

        return NextResponse.json({ topics })
    } catch (e: any) {
        console.error('Failed to get topics queue:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// POST: AI를 활용한 카테고리별 주제 자동 생성 발굴 엔진 실행
export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { categoryId } = await req.json()
        if (!categoryId) {
            return NextResponse.json({ error: 'Missing categoryId' }, { status: 400 })
        }

        const supabase = getAdmin()
        
        // 1. 카테고리 정보 로드
        const { data: category, error: catError } = await supabase
            .from('categories')
            .select('*')
            .eq('id', categoryId)
            .single()

        if (catError || !category) {
            return NextResponse.json({ error: 'Category not found' }, { status: 404 })
        }

        // 2. Gemini API Key 로드 (환경변수 또는 대표님 API Key)
        // Vercel 환경에 세팅된 GEMINI_API_KEY 사용 후, 없을 시 DB global_settings에서 백업본 로드
        let geminiApiKey = process.env.GEMINI_API_KEY
        if (!geminiApiKey) {
            const { data: dbKey } = await supabase
                .from('global_settings')
                .select('value')
                .eq('key', 'sys_api_gemini')
                .maybeSingle()
            if (dbKey?.value) {
                geminiApiKey = dbKey.value
            }
        }
        
        if (!geminiApiKey) {
            return NextResponse.json({ error: 'Gemini API Key is not configured on the server (Neither environment variable nor sys_api_gemini is present in global_settings)' }, { status: 500 })
        }

        const { data: policyRows } = await supabase
            .from('global_settings')
            .select('key,value')
            .in('key', [
                'sys_api_longform_min_duration_minutes',
                'sys_api_longform_base_payout',
                'sys_api_longform_extra_minute_payout',
                'sys_api_longform_duration_lock_enabled'
            ])
        const policy = Object.fromEntries((policyRows || []).map((row: any) => [row.key, row.value]))
        const minDurationMinutes = Math.max(15, toInt(policy.sys_api_longform_min_duration_minutes, 15))
        const basePayout = Math.max(0, toInt(policy.sys_api_longform_base_payout, 10000))
        const extraMinutePayout = Math.max(0, toInt(policy.sys_api_longform_extra_minute_payout, 500))
        const durationLockEnabled = String(policy.sys_api_longform_duration_lock_enabled ?? 'true') !== 'false'
        const isLongformCategory = (category.video_type || 'longform') === 'longform'
        const targetLang = normalizeContentLanguage(category.language)
        const preferredWorkers = await loadPreferredWorkers(supabase)

        // 이 카테고리에 이미 쌓여있는 주제 목록을 프롬프트에 넣어 "겹치는 주제 반복 생성"을
        // 막는다. 이게 없으면 같은 카테고리에서 여러 번 생성 버튼을 누를 때마다 AI가
        // 매번 가장 뻔한 각도로 비슷한 10개를 다시 뽑아내는 문제가 있었다.
        const { data: existingTopicRows, count: existingTopicCount } = await supabase
            .from('topics_queue')
            .select('topic', { count: 'exact' })
            .eq('category_id', categoryId)
            .in('status', ['pending', 'assigned', 'completed'])
            .order('created_at', { ascending: false })
            .limit(80)
        const existingTopics = Array.from(new Set(
            (existingTopicRows || [])
                .map((row: any) => String(row.topic || '').trim())
                .filter(Boolean)
        ))

        // [AIR-0230] 실제 구독자 대비 고성과 영상을 분석한 결과가 있으면(§2b 수동/자동
        // 트리거로 생성됨, remote_hermes_queue) 프롬프트에 근거로 넣고, 생성되는 각 주제에도
        // 실어서 나중에 대본기획 단계(scene_planner.py)까지 전달되게 한다. 없으면 그냥
        // 기존 방식(카테고리 이름/키워드/벤치마크 채널 텍스트)만 사용 - 이 조회 자체가
        // 실패해도 주제 생성 자체를 막지 않는다.
        let benchmarkAnalysis: any = null
        try {
            const { data: benchmarkRow } = await supabase
                .from('remote_hermes_queue')
                .select('result_payload, completed_at')
                .eq('category_id', String(categoryId))
                .eq('job_type', 'topic_benchmark_analyze')
                .eq('status', 'completed')
                .order('completed_at', { ascending: false })
                .limit(1)
                .maybeSingle()
            benchmarkAnalysis = benchmarkRow?.result_payload ?? null
        } catch (e) {
            console.warn('[Topic Generator] benchmark analysis lookup failed (continuing without it):', e)
        }

        console.log(`Running AI Auto-Topic Generator for category: ${category.name}`);
        const nowInKst = new Date()
        const currentDateKst = new Intl.DateTimeFormat('en-CA', {
            timeZone: 'Asia/Seoul',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        }).format(nowInKst)
        const currentYearKst = currentDateKst.slice(0, 4)
        
        // 3. 트렌드 분석 및 10개 주제 생성 (데모 속도를 위해 10개씩 벌크 생성).
        // AIR-0225: 웹어드민 "주제 추천 모델" 설정(sys_api_topic_generation_model)에
        // 따라 Claude/Gemini를 자동 라우팅한다 - 예전엔 이 설정과 무관하게 항상 Gemini만 썼다.
        const prompt = `
        You are an expert YouTube Content Planner.
        Today's date in Korea is ${currentDateKst}.
        The current year is ${currentYearKst}.
        Target content language: ${contentLanguageLabel(targetLang)} (${targetLang}).
        Category Name: ${category.name}
        Keywords: ${category.keywords}
        Benchmark Channel: ${category.benchmark_channel_url}

        Generate exactly 10 high-performance, viral, click-worthy video topics for YouTube Shorts or Longform videos based on the category name, keywords, and benchmark references.

        ${topicLanguageInstruction(targetLang)}

        CRITICAL GUIDELINES:
        - The generated topics MUST be the actual titles or subjects of the video itself (e.g., actual traditional folktales, historical anecdotes, heartwarming life stories, legends) that the target viewers will watch and listen to directly.
        - NEVER generate meta-topics, channel marketing strategies, target audience analysis, or video production tips.
        - If the category is about storytelling, history, or old stories, generate actual compelling story titles or narrative topics.

        - For finance, economy, investment, stock, real-estate, news, current-affairs, and trend-sensitive categories, use the present-time context of ${currentYearKst}.
        - If a year is mentioned in a current-affairs or market topic, prefer ${currentYearKst}. Do not generate stale present-tense titles anchored to 2024 or 2025 unless the topic is explicitly retrospective or historical.
        - If the input keywords contain older years, treat them only as weak reference context and rewrite the final title so it matches ${currentYearKst}.

        DIVERSITY REQUIREMENT (this category already has a repetition problem — take it seriously):
        - The 10 topics must span at least 5 clearly different angles or sub-types (for example: a specific historical event, a personal/family life story, a mysterious or unexplained case, a ranking/listicle compilation, a cautionary or moral tale, a surprising little-known fact, a comparison, an emotional human-interest drama — pick whichever angles genuinely fit this category).
        - Do NOT produce 10 topics that all follow the same sentence pattern, structure, or opening phrase.
        - Do NOT produce near-duplicate topics within this same batch of 10 (same core subject with only wording changed).
        ${existingTopics.length ? `
        EXISTING TOPICS ALREADY IN THIS CATEGORY'S QUEUE (${existingTopicCount ?? existingTopics.length} total in this category; ${existingTopics.length} most recent shown below) — DO NOT repeat any of these, and do NOT generate a near-duplicate or a minor rewording of any of them:
        ${existingTopics.map((t) => `- ${t}`).join('\n        ')}
        ` : ''}
        ${benchmarkAnalysis?.candidates?.length ? `
        REAL HIGH-PERFORMING VIDEO EVIDENCE (actual YouTube videos in this niche, ranked by views-vs-subscribers, analyzed by AI — use this as REAL evidence of what currently works, not just a guess):
        ${benchmarkAnalysis.candidates.map((c: any) => {
            const a = c?.analysis || {}
            const sa = a?.script_analysis || {}
            return `- "${c.title}" (performance ${c.performance_ratio}x views-to-subscribers): hooks="${sa.hooks || ''}", structure="${sa.structure || ''}", viewer needs=${JSON.stringify(a.viewer_needs || [])}`
        }).join('\n        ')}
        Use this to inform the ANGLE/HOOK STYLE of the 10 topics you generate — but do not copy this video's title, names, or specific plot; only its technique.
        ` : ''}

        ${isLongformCategory ? `
        For each LONGFORM topic, also choose a realistic target video duration in minutes.
        Rules:
        - Minimum duration is ${minDurationMinutes} minutes.
        - Use 15 minutes for compact, simple stories.
        - Use 20-25 minutes for normal narrative/explainer topics.
        - Use 30-40 minutes only for complex history, multi-case, deep-investigation, or documentary topics.
        - Do not choose a duration just to increase pay; choose based on natural content depth.
        ` : ''}

        STYLE SELECTION (REQUIRED for every topic):
        - For each topic, also choose the BEST matching script_style for that specific topic.
        - script_style MUST be exactly one of: ${SCRIPT_STYLE_KEYS.join(', ')}.
        - Choose a style that fits the topic's mood, era, and genre (e.g. horror/thriller topics -> mystery_thriller/horror_suspense; Joseon-era history -> joseon_sageuk; children's content -> nursery_rhyme; modern news/economy -> news).
        - If unsure, use "${DEFAULT_SCRIPT_STYLE}".
        - Use ONLY the exact keys from the list above. Never invent new style keys.
        - Do NOT choose an image_style — that is set per-category by an admin, not per-topic by AI.

        Provide the output as JSON, with absolutely no markdown formatting.
        ${isLongformCategory ? `
        Return a JSON list of objects with keys: topic, recommended_duration_minutes, difficulty_level, duration_reason, script_style.
        Example output format:
        [
          {
            "topic": "${targetLang === 'en' ? 'The Untold Story That Changed a Family Forever' : targetLang === 'ja' ? '家族の運命を変えた、知られざる物語' : '첫 번째 실제 동영상 주제'}",
            "recommended_duration_minutes": 20,
            "difficulty_level": "normal",
            "duration_reason": "${targetLang === 'en' ? 'The topic needs enough time for background and emotional payoff.' : targetLang === 'ja' ? '背景説明と感情の盛り上がりに十分な尺が必要なため。' : '스토리의 깊이와 배경 설명이 필요한 주제'}",
            "script_style": "story"
          }
        ]
        ` : `
        Return a JSON list of objects with keys: topic, script_style.
        Example output format:
        [
          {
            "topic": "${targetLang === 'en' ? 'A Short Story You Will Never Forget' : targetLang === 'ja' ? '忘れられない短い物語' : '첫 번째 실제 동영상 주제'}",
            "script_style": "default"
          }
        ]
        `}
        `

        // AIR: 다양성 확보를 위해 창의성(temperature)을 명시적으로 올려서 호출한다.
        // 번역 등 다른 generateJsonWithModelSetting 호출부는 temperature를 넘기지 않으므로
        // 이 변경의 영향을 받지 않는다 (기존 결정적 동작 그대로 유지).
        const text = await generateJsonWithModelSetting(
            supabase,
            prompt,
            'sys_api_topic_generation_model',
            geminiApiKey,
            1.0
        )
        const topics = JSON.parse(text)

        if (!Array.isArray(topics) || topics.length === 0) {
            throw new Error('AI returned an invalid topics format.')
        }

        // 4. Supabase topics_queue 에 적재
        const inserts = topics.map(item => {
            const topic = typeof item === 'string' ? item : item?.topic
            const geminiDuration = isLongformCategory
                ? clampDuration(item?.recommended_duration_minutes, minDurationMinutes)
                : null

            // AI가 주제에 맞게 고른 대본 스타일 (허용 목록 검증 + 기본값 fallback)
            const assignedScriptStyle = pickValidStyle(
                typeof item === 'string' ? null : item?.script_style,
                SCRIPT_STYLE_KEYS,
                DEFAULT_SCRIPT_STYLE
            )
            // 이미지 스타일은 더 이상 AI가 주제 단위로 추측하지 않는다 — 관리자가 카테고리에
            // 지정한 default_image_style을 그대로 쓴다 (거의 항상 realistic만 나오던 문제 해결).
            const assignedImageStyle = pickValidStyle(
                category.default_image_style,
                IMAGE_STYLE_KEYS,
                DEFAULT_IMAGE_STYLE
            )

            // 배정 대상 워커를 먼저 결정한 뒤, 그 워커의 선호 영상 길이에 맞게 duration을 보정한다.
            const worker = pickPreferredWorker(
                preferredWorkers,
                category.assigned_employee_email,
                category.id,
                geminiDuration,
                isLongformCategory,
                targetLang
            )
            const assignedEmployeeEmail = worker?.email || null

            const assignedDuration = (isLongformCategory && geminiDuration != null)
                ? adjustToBucket(geminiDuration, worker?.preferredVideoLength || '', minDurationMinutes)
                : geminiDuration
            const estimatedPayout = assignedDuration
                ? payoutForMinutes(assignedDuration, minDurationMinutes, basePayout, extraMinutePayout)
                : null

            return {
                category_id: category.id,
                topic: String(topic || '').trim(),
                assigned_employee_email: assignedEmployeeEmail,
                assigned_script_style: assignedScriptStyle,
                assigned_image_style: assignedImageStyle,
                language: targetLang,
                status: 'pending',
                translation_status: 'pending',
                // [AIR-0230] 이 카테고리의 실제 고성과 영상 분석이 있으면 주제마다 실어서
                // claim_topic() → project_settings → scene_planner.py까지 전달되게 한다
                // (migrations/air_0230_topics_queue_benchmark_analysis_column.sql, 미적용 초안).
                benchmark_analysis: benchmarkAnalysis,
                ...(isLongformCategory ? {
                    recommended_duration_minutes: assignedDuration,
                    assigned_duration_minutes: assignedDuration,
                    duration_locked: durationLockEnabled,
                    estimated_payout: estimatedPayout,
                    payout_policy: {
                        min_duration_minutes: minDurationMinutes,
                        base_payout: basePayout,
                        extra_minute_payout: extraMinutePayout
                    },
                    duration_reason: typeof item === 'string' ? '' : (item?.duration_reason || ''),
                    difficulty_level: typeof item === 'string' ? 'normal' : (item?.difficulty_level || 'normal')
                } : {})
            }
        }).filter(item => item.topic)

        // AIR-0129: select back inserted IDs to kick off background translation
        let { data: insertedRows, error: insertError } = await supabase
            .from('topics_queue')
            .insert(inserts)
            .select('id')

        // 신규 컬럼이 아직 Supabase 스키마에 반영되지 않은 환경에서만 fallback으로 재시도한다.
        if (isMissingColumnError(insertError)) {
            const fallbackInserts = inserts.map(({ recommended_duration_minutes, assigned_duration_minutes, duration_locked, estimated_payout, payout_policy, duration_reason, difficulty_level, assigned_script_style, assigned_image_style, language, translation_status, benchmark_analysis, ...rest }: any) => rest)
            const retry = await supabase
                .from('topics_queue')
                .insert(fallbackInserts)
                .select('id')
            insertedRows = retry.data
            insertError = retry.error
        }

        if (insertError) throw insertError

        // Fire background translation (non-blocking — admin save returns immediately)
        const insertedIds = (insertedRows || []).map((r: any) => String(r.id))
        if (insertedIds.length && geminiApiKey) {
            void translateAndSaveTopics(insertedIds, supabase, geminiApiKey)
        }

        return NextResponse.json({ success: true, count: inserts.length, topics })
    } catch (e: any) {
        console.error('AI Topic Generation engine failed:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PUT: 대기중 주제 제목 수정
export async function PUT(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { id, topic } = await req.json()

        if (!id || !String(topic || '').trim()) {
            return NextResponse.json({ error: 'Missing id or topic' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data: existing, error: existingError } = await supabase
            .from('topics_queue')
            .select('id, status, category_id')
            .eq('id', id)
            .single()

        if (existingError || !existing) {
            return NextResponse.json({ error: 'Topic not found' }, { status: 404 })
        }

        if (existing.status !== 'pending') {
            return NextResponse.json({ error: 'Only pending topics can be edited' }, { status: 400 })
        }

        // AIR-0129: Reset translation columns + set pending so background translation restarts.
        // Falls back to topic-only update if migration has not been applied yet.
        const updatePayload: Record<string, string | null> = {
            topic: String(topic).trim(),
            topic_vi: null,
            topic_en: null,
            topic_th: null,
            category_name_vi: null,
            category_name_en: null,
            category_name_th: null,
            translation_status: 'pending',
        }
        let { data, error } = await supabase
            .from('topics_queue')
            .update(updatePayload)
            .eq('id', id)
            .select('id, category_id, topic, status')
            .single()

        if (isMissingColumnError(error)) {
            // Translation columns not yet migrated — update topic text only.
            const retry = await supabase
                .from('topics_queue')
                .update({ topic: String(topic).trim() })
                .eq('id', id)
                .select('id, category_id, topic, status')
                .single()
            data = retry.data
            error = retry.error
        }

        if (error) throw error

        // Fire background translation (non-blocking — admin save returns immediately)
        let putGeminiApiKey = process.env.GEMINI_API_KEY
        if (!putGeminiApiKey) {
            const { data: dbKey } = await supabase
                .from('global_settings')
                .select('value')
                .eq('key', 'sys_api_gemini')
                .maybeSingle()
            if (dbKey?.value) putGeminiApiKey = dbKey.value
        }
        if (putGeminiApiKey) {
            void translateAndSaveTopics([String(id)], supabase, putGeminiApiKey)
        }

        return NextResponse.json({ success: true, topic: data })
    } catch (e: any) {
        console.error('Failed to update topic queue item:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 대기중 주제 삭제
export async function DELETE(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        const categoryId = searchParams.get('categoryId')
        const yearsRaw = searchParams.get('years')
        const deleteAll = searchParams.get('all') === 'true'

        // 카테고리 단위 일괄 삭제: years가 있으면 해당 연도만, 없고 all=true면
        // 그 카테고리의 대기중(pending) 주제 전체를 지운다 (뻔하고 비슷한 주제가
        // 잔뜩 쌓였을 때 하나씩 지우지 않고 한 번에 정리하기 위한 기능).
        if (categoryId && (yearsRaw || deleteAll)) {
            const supabase = getAdmin()
            let selectQuery = supabase
                .from('topics_queue')
                .select('id, topic')
                .eq('category_id', categoryId)
                .eq('status', 'pending')

            if (yearsRaw) {
                const years = yearsRaw
                    .split(',')
                    .map(value => value.trim())
                    .filter(Boolean)

                if (years.length === 0) {
                    return NextResponse.json({ error: 'Missing cleanup years' }, { status: 400 })
                }

                const yearFilters = years
                    .map(year => `topic.ilike.%${year}%`)
                    .join(',')

                selectQuery = selectQuery.or(yearFilters)
            }

            const { data: candidates, error: selectError } = await selectQuery

            if (selectError) throw selectError

            if (!candidates || candidates.length === 0) {
                return NextResponse.json({ success: true, deletedCount: 0, deletedIds: [] })
            }

            const ids = candidates.map(item => item.id)
            const { error } = await supabase
                .from('topics_queue')
                .delete()
                .in('id', ids)

            if (error) throw error

            return NextResponse.json({ success: true, deletedCount: ids.length, deletedIds: ids })
        }

        if (!id) {
            return NextResponse.json({ error: 'Missing id' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data: existing, error: existingError } = await supabase
            .from('topics_queue')
            .select('id, status')
            .eq('id', id)
            .single()

        if (existingError || !existing) {
            return NextResponse.json({ error: 'Topic not found' }, { status: 404 })
        }

        if (existing.status !== 'pending') {
            return NextResponse.json({ error: 'Only pending topics can be deleted' }, { status: 400 })
        }

        const { error } = await supabase
            .from('topics_queue')
            .delete()
            .eq('id', id)

        if (error) throw error

        return NextResponse.json({ success: true, id })
    } catch (e: any) {
        console.error('Failed to delete topic queue item:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PATCH: 대기중 주제의 대본 스타일을 AI로 재배정
// 이미지 스타일은 더 이상 AI가 주제 단위로 추측하지 않는다 — 카테고리별 default_image_style을
// 관리자가 직접 지정한다 (거의 항상 realistic만 나오던 문제로 폐지, [스타일세팅] 참고).
export async function PATCH(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { targetType, categoryId, limit } = await req.json()
        const normalizedTarget = String(targetType || '').trim().toLowerCase()

        if (normalizedTarget !== 'script') {
            return NextResponse.json({ error: 'targetType must be script (image style is admin-managed per category, not AI-assigned)' }, { status: 400 })
        }

        const supabase = getAdmin()
        let geminiApiKey = process.env.GEMINI_API_KEY
        if (!geminiApiKey) {
            const { data: dbKey } = await supabase
                .from('global_settings')
                .select('value')
                .eq('key', 'sys_api_gemini')
                .maybeSingle()
            if (dbKey?.value) {
                geminiApiKey = dbKey.value
            }
        }

        if (!geminiApiKey) {
            return NextResponse.json({ error: 'Gemini API Key is not configured.' }, { status: 500 })
        }

        const batchLimit = Math.max(1, Math.min(100, toInt(limit, 50)))
        let query = supabase
            .from('topics_queue')
            .select('id, topic, category_id, language, assigned_script_style, categories(name, keywords, language)')
            .eq('status', 'pending')
            .order('created_at', { ascending: false })
            .limit(batchLimit)

        if (categoryId && String(categoryId) !== 'all') {
            query = query.eq('category_id', categoryId)
        }

        const { data: rows, error: loadError } = await query
        if (loadError) throw loadError

        const topics = rows || []
        if (!topics.length) {
            return NextResponse.json({ success: true, updatedCount: 0, updates: [] })
        }

        const allowedStyles = SCRIPT_STYLE_KEYS
        const fallbackStyle = DEFAULT_SCRIPT_STYLE
        const styleColumn = 'assigned_script_style'
        const ai = new GoogleGenAI({ apiKey: geminiApiKey })
        const prompt = `
You are assigning the best ${normalizedTarget}_style for queued YouTube topics.
Return ONLY valid JSON. No markdown.

Allowed style keys: ${allowedStyles.join(', ')}
Fallback style: ${fallbackStyle}

Rules:
- Choose exactly one allowed key for each topic.
- Match the topic's mood, era, genre, target audience, and content language.
- If uncertain, use the fallback style.
- Do not invent style keys.

Topics:
${topics.map((item: any, index: number) => {
            const category = item.categories?.name || ''
            const keywords = item.categories?.keywords || ''
            const lang = normalizeContentLanguage(item.language || item.categories?.language)
            return `${index + 1}. id=${item.id}; language=${contentLanguageLabel(lang)}; category=${category}; keywords=${keywords}; topic=${item.topic}`
        }).join('\n')}

Return format:
[
  {"id":"topic id", "style":"one_allowed_key"}
]
        `.trim()

        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: prompt,
            config: { responseMimeType: 'application/json' }
        })

        const parsed = JSON.parse(response.text || '[]')
        if (!Array.isArray(parsed)) {
            throw new Error('AI returned an invalid style assignment format.')
        }

        const byId = new Map(parsed.map((item: any) => [String(item?.id), pickValidStyle(item?.style, allowedStyles, fallbackStyle)]))
        const updates = topics.map((item: any) => ({
            id: item.id,
            style: byId.get(String(item.id)) || fallbackStyle
        }))

        await Promise.all(updates.map(item =>
            supabase
                .from('topics_queue')
                .update({ [styleColumn]: item.style })
                .eq('id', item.id)
        ))

        return NextResponse.json({
            success: true,
            targetType: normalizedTarget,
            updatedCount: updates.length,
            updates,
        })
    } catch (e: any) {
        console.error('Failed to assign topic styles:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
