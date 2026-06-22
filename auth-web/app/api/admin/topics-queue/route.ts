import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { GoogleGenAI } from '@google/genai'

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
    activeLoad: number
}

async function loadPreferredWorkers(supabase: ReturnType<typeof getAdmin>): Promise<PreferredWorker[]> {
    const { data: profiles, error: profilesError } = await supabase
        .from('profiles')
        .select('email,is_approved,preferred_category_ids,preferred_video_length')

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
            return {
                email,
                preferredCategoryIds: toStringArray(profile.preferred_category_ids),
                preferredVideoLength: String(profile.preferred_video_length || '').trim(),
                activeLoad: loadMap.get(email) || 0,
            }
        })
}

function pickPreferredWorker(
    workers: PreferredWorker[],
    fallbackEmail: string,
    categoryId: any,
    durationMinutes: number | null,
    isLongformCategory: boolean
): PreferredWorker | null {
    const fallback = String(fallbackEmail || '').trim().toLowerCase()
    const targetCategoryId = String(categoryId ?? '').trim()
    if (!targetCategoryId) return null

    const categoryMatched = workers.filter((worker) => worker.preferredCategoryIds.includes(targetCategoryId))
    if (!categoryMatched.length) return null

    const targetBucket = isLongformCategory ? durationPreferenceBucket(durationMinutes) : ''
    const ranked = [...categoryMatched].sort((a, b) => {
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

    return {
        ...topic,
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
            query = query.eq('status', status)
        }

        const { data, error } = await query

        if (error) throw error

        let topics = data || []

        // 카테고리 담당자 정보가 정답이다. 오래된 topics_queue row가 다른 이메일을 들고 있으면
        // 관리자 화면과 실제 배당 기준이 어긋나므로 조회 시 자동으로 보정한다.
        const mismatchedTopics = topics.filter((topic: any) => {
            const categoryEmail = topic.categories?.assigned_employee_email
            return categoryEmail && topic.assigned_employee_email !== categoryEmail
        })

        await Promise.all(
            mismatchedTopics.map((topic: any) =>
                supabase
                    .from('topics_queue')
                    .update({ assigned_employee_email: topic.categories.assigned_employee_email })
                    .eq('id', topic.id)
            )
        )

        topics = topics.map((topic: any) => normalizeTopicQueueRow({
            ...topic,
            assigned_employee_email: topic.categories?.assigned_employee_email || topic.assigned_employee_email
        }))

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
        const preferredWorkers = await loadPreferredWorkers(supabase)

        console.log(`Running AI Auto-Topic Generator for category: ${category.name}`);
        const nowInKst = new Date()
        const currentDateKst = new Intl.DateTimeFormat('en-CA', {
            timeZone: 'Asia/Seoul',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        }).format(nowInKst)
        const currentYearKst = currentDateKst.slice(0, 4)
        
        // 3. Gemini를 사용한 트렌드 분석 및 10개 주제 생성 (데모 속도를 위해 10개씩 벌크 생성)
        const ai = new GoogleGenAI({ apiKey: geminiApiKey })
        const prompt = `
        You are an expert YouTube Content Planner.
        Today's date in Korea is ${currentDateKst}.
        The current year is ${currentYearKst}.
        Category Name: ${category.name}
        Keywords: ${category.keywords}
        Benchmark Channel: ${category.benchmark_channel_url}

        Generate exactly 10 high-performance, viral, click-worthy video topics for YouTube Shorts or Longform videos based on the category name, keywords, and benchmark references.
        
        CRITICAL GUIDELINES:
        - The generated topics MUST be the actual titles or subjects of the video itself (e.g., actual traditional folktales, historical anecdotes, heartwarming life stories, legends) that the target viewers will watch and listen to directly.
        - NEVER generate meta-topics, channel marketing strategies, target audience analysis, or video production tips (e.g., DO NOT generate topics like "조회수 터지는 옛날이야기 채널, 진짜 타겟은 누구일까?" or "유튜브 쇼츠 조회수 올리는 법").
        - If the category is about storytelling, history, or old stories, generate actual compelling story titles or narrative topics (e.g., "은혜 갚은 호랑이와 나무꾼의 슬픈 사연", "조선 시대 백성들을 울린 희대의 판결", "평생 고생한 자식에게 전하는 눈물 나는 인생 조언").
        
        - For finance, economy, investment, stock, real-estate, news, current-affairs, and trend-sensitive categories, use the present-time context of ${currentYearKst}.
        - If a year is mentioned in a current-affairs or market topic, prefer ${currentYearKst}. Do not generate stale present-tense titles anchored to 2024 or 2025 unless the topic is explicitly retrospective or historical.
        - If the input keywords contain older years, treat them only as weak reference context and rewrite the final title so it matches ${currentYearKst}.

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
        - For each topic, also choose the BEST matching script_style and image_style for that specific topic.
        - script_style MUST be exactly one of: ${SCRIPT_STYLE_KEYS.join(', ')}.
        - image_style MUST be exactly one of: ${IMAGE_STYLE_KEYS.join(', ')}.
        - Choose styles that fit the topic's mood, era, and genre (e.g. horror/thriller topics -> mystery_thriller/horror_suspense + cinematic; Joseon-era history -> joseon_sageuk + oriental_ink; children's content -> nursery_rhyme + nursery_rhyme; modern news/economy -> news + realistic).
        - If unsure, use "${DEFAULT_SCRIPT_STYLE}" for script_style and "${DEFAULT_IMAGE_STYLE}" for image_style.
        - Use ONLY the exact keys from the lists above. Never invent new style keys.

        Provide the output in Korean as JSON, with absolutely no markdown formatting.
        ${isLongformCategory ? `
        Return a JSON list of objects with keys: topic, recommended_duration_minutes, difficulty_level, duration_reason, script_style, image_style.
        Example output format:
        [
          {
            "topic": "첫 번째 실제 동영상 주제",
            "recommended_duration_minutes": 20,
            "difficulty_level": "normal",
            "duration_reason": "스토리의 깊이와 역사적 배경 설명이 필요한 주제",
            "script_style": "story",
            "image_style": "cinematic"
          }
        ]
        ` : `
        Return a JSON list of objects with keys: topic, script_style, image_style.
        Example output format:
        [
          {
            "topic": "첫 번째 실제 동영상 주제",
            "script_style": "default",
            "image_style": "realistic"
          }
        ]
        `}
        `

        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: prompt,
            config: {
                responseMimeType: 'application/json'
            }
        })

        const text = response.text || '[]'
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

            // AI가 주제에 맞게 고른 스타일 (허용 목록 검증 + 기본값 fallback)
            const assignedScriptStyle = pickValidStyle(
                typeof item === 'string' ? null : item?.script_style,
                SCRIPT_STYLE_KEYS,
                DEFAULT_SCRIPT_STYLE
            )
            const assignedImageStyle = pickValidStyle(
                typeof item === 'string' ? null : item?.image_style,
                IMAGE_STYLE_KEYS,
                DEFAULT_IMAGE_STYLE
            )

            // 배정 대상 워커를 먼저 결정한 뒤, 그 워커의 선호 영상 길이에 맞게 duration을 보정한다.
            const worker = pickPreferredWorker(
                preferredWorkers,
                category.assigned_employee_email,
                category.id,
                geminiDuration,
                isLongformCategory
            )
            const assignedEmployeeEmail = worker?.email || String(category.assigned_employee_email || '').trim().toLowerCase()

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
                status: 'pending',
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

        let { error: insertError } = await supabase
            .from('topics_queue')
            .insert(inserts)

        // 신규 컬럼이 아직 Supabase 스키마에 반영되지 않은 환경에서만 fallback으로 재시도한다.
        // 기존 정규식은 "duration"/"style" 같은 단어가 들어간 무관한 오류까지 잡아 데이터를 누락시켰다.
        // PostgREST 스키마 캐시 누락(PGRST204) / Postgres undefined_column(42703) / 명시적 컬럼 부재 메시지만 매칭한다.
        const isMissingColumnError = (err: any): boolean => {
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

        if (isMissingColumnError(insertError)) {
            const fallbackInserts = inserts.map(({ recommended_duration_minutes, assigned_duration_minutes, duration_locked, estimated_payout, payout_policy, duration_reason, difficulty_level, assigned_script_style, assigned_image_style, ...rest }: any) => rest)
            const retry = await supabase
                .from('topics_queue')
                .insert(fallbackInserts)
            insertError = retry.error
        }

        if (insertError) throw insertError

        return NextResponse.json({ success: true, count: inserts.length, topics })
    } catch (e: any) {
        console.error('AI Topic Generation engine failed:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PUT: 대기중 주제 제목 수정
export async function PUT(req: Request) {
    try {
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

        const { data, error } = await supabase
            .from('topics_queue')
            .update({ topic: String(topic).trim() })
            .eq('id', id)
            .select('id, category_id, topic, status')
            .single()

        if (error) throw error

        return NextResponse.json({ success: true, topic: data })
    } catch (e: any) {
        console.error('Failed to update topic queue item:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 대기중 주제 삭제
export async function DELETE(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        const categoryId = searchParams.get('categoryId')
        const yearsRaw = searchParams.get('years')

        if (categoryId && yearsRaw) {
            const years = yearsRaw
                .split(',')
                .map(value => value.trim())
                .filter(Boolean)

            if (years.length === 0) {
                return NextResponse.json({ error: 'Missing cleanup years' }, { status: 400 })
            }

            const supabase = getAdmin()
            const yearFilters = years
                .map(year => `topic.ilike.%${year}%`)
                .join(',')

            const selectQuery = supabase
                .from('topics_queue')
                .select('id, topic')
                .eq('category_id', categoryId)
                .eq('status', 'pending')
                .or(yearFilters)

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

// PATCH: 대기중 주제의 대본/이미지 스타일을 AI로 재배정
export async function PATCH(req: Request) {
    try {
        const { targetType, categoryId, limit } = await req.json()
        const normalizedTarget = String(targetType || '').trim().toLowerCase()

        if (!['script', 'image'].includes(normalizedTarget)) {
            return NextResponse.json({ error: 'targetType must be script or image' }, { status: 400 })
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
            .select('id, topic, category_id, assigned_script_style, assigned_image_style, categories(name, keywords)')
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

        const allowedStyles = normalizedTarget === 'script' ? SCRIPT_STYLE_KEYS : IMAGE_STYLE_KEYS
        const fallbackStyle = normalizedTarget === 'script' ? DEFAULT_SCRIPT_STYLE : DEFAULT_IMAGE_STYLE
        const styleColumn = normalizedTarget === 'script' ? 'assigned_script_style' : 'assigned_image_style'
        const ai = new GoogleGenAI({ apiKey: geminiApiKey })
        const prompt = `
You are assigning the best ${normalizedTarget}_style for queued YouTube topics.
Return ONLY valid JSON. No markdown.

Allowed style keys: ${allowedStyles.join(', ')}
Fallback style: ${fallbackStyle}

Rules:
- Choose exactly one allowed key for each topic.
- Match the topic's mood, era, genre, and target audience.
- If uncertain, use the fallback style.
- Do not invent style keys.

Topics:
${topics.map((item: any, index: number) => {
            const category = item.categories?.name || ''
            const keywords = item.categories?.keywords || ''
            return `${index + 1}. id=${item.id}; category=${category}; keywords=${keywords}; topic=${item.topic}`
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
