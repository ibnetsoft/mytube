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
        const status = searchParams.get('status') || 'pending'

        const supabase = getAdmin()
        let query = supabase
            .from('topics_queue')
            .select('*, categories(*)')
            .order('created_at', { ascending: false })

        if (email) {
            query = query.eq('assigned_employee_email', email)
        }
        if (status) {
            query = query.eq('status', status)
        }

        const { data, error } = await query

        if (error) throw error

        return NextResponse.json({ topics: data || [] })
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
        
        // 3. Gemini를 사용한 트렌드 분석 및 10개 주제 생성 (데모 속도를 위해 10개씩 벌크 생성)
        const ai = new GoogleGenAI({ apiKey: geminiApiKey })
        const prompt = `
        You are an expert YouTube Content Planner. 
        Category Name: ${category.name}
        Keywords: ${category.keywords}
        Benchmark Channel: ${category.benchmark_channel_url}

        Generate exactly 10 high-performance, viral, click-worthy video topics for YouTube Shorts or Longform videos based on the category name, keywords, and benchmark references.
        
        CRITICAL GUIDELINES:
        - The generated topics MUST be the actual titles or subjects of the video itself (e.g., actual traditional folktales, historical anecdotes, heartwarming life stories, legends) that the target viewers will watch and listen to directly.
        - NEVER generate meta-topics, channel marketing strategies, target audience analysis, or video production tips (e.g., DO NOT generate topics like "조회수 터지는 옛날이야기 채널, 진짜 타겟은 누구일까?" or "유튜브 쇼츠 조회수 올리는 법").
        - If the category is about storytelling, history, or old stories, generate actual compelling story titles or narrative topics (e.g., "은혜 갚은 호랑이와 나무꾼의 슬픈 사연", "조선 시대 백성들을 울린 희대의 판결", "평생 고생한 자식에게 전하는 눈물 나는 인생 조언").
        
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
