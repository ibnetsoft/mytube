import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { GoogleGenAI } from '@google/genai'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

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

        topics = topics.map((topic: any) => ({
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

        Provide the output in Korean as a JSON list of strings, with absolutely no markdown formatting.
        Example output format:
        [
          "첫 번째 실제 동영상 주제",
          "두 번째 실제 동영상 주제"
        ]
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
        const inserts = topics.map(topic => ({
            category_id: category.id,
            topic: String(topic),
            assigned_employee_email: category.assigned_employee_email,
            status: 'pending'
        }))

        const { error: insertError } = await supabase
            .from('topics_queue')
            .insert(inserts)

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
