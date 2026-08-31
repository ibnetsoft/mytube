import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin, SUPER_ADMIN_EMAIL } from '../_auth'
import { deleteServerCache, getServerCache, setServerCache } from '@/lib/server-cache'

const CATEGORIES_CACHE_KEY = 'admin:categories'
const CATEGORIES_CACHE_TTL_SECONDS = 300
const RETIRED_CATEGORY_NAMES = new Set(['노후금융', '경제'])
const RETIRED_CATEGORY_IDS = new Set([3, 8])

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const CONTENT_LANGUAGES = ['ko', 'en', 'ja'] as const

type ContentLanguage = typeof CONTENT_LANGUAGES[number]

function normalizeContentLanguage(value: any): ContentLanguage {
    const lang = String(value || '').trim().toLowerCase()
    return CONTENT_LANGUAGES.includes(lang as ContentLanguage) ? lang as ContentLanguage : 'ko'
}

function isMissingColumnError(err: any): boolean {
    if (!err) return false
    const code = String(err.code || '')
    if (code === 'PGRST204' || code === '42703') return true
    const msg = String(err.message || '').toLowerCase()
    return msg.includes('schema cache') || /could not find the .* column/.test(msg) || /column .* does not exist/.test(msg)
}

// GET: 카테고리 목록 조회
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const cached = await getServerCache<{ categories: any[] }>(CATEGORIES_CACHE_KEY)
        if (cached) {
            return NextResponse.json(cached, {
                headers: {
                    'Cache-Control': `private, max-age=${CATEGORIES_CACHE_TTL_SECONDS}`,
                    'X-Admin-Cache': 'HIT',
                },
            })
        }

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('categories')
            .select('*')
            .order('created_at', { ascending: false })

        if (error) throw error

        const response = {
            categories: (data || [])
                .filter((category: any) => (
                    !RETIRED_CATEGORY_NAMES.has(String(category.name || '').trim())
                    && !RETIRED_CATEGORY_IDS.has(Number(category.id))
                ))
                .map((category: any) => ({
                    ...category,
                    language: normalizeContentLanguage(category.language),
                }))
        }
        await setServerCache(CATEGORIES_CACHE_KEY, response, CATEGORIES_CACHE_TTL_SECONDS)

        return NextResponse.json(response, {
            headers: {
                'Cache-Control': `private, max-age=${CATEGORIES_CACHE_TTL_SECONDS}`,
                'X-Admin-Cache': 'MISS',
            },
        })
    } catch (e: any) {
        console.error('Failed to get categories:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// POST: 카테고리 생성
export async function POST(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const {
            name,
            keywords,
            benchmark_channel_url,
            assigned_employee_email,
            default_script_style,
            default_image_style,
            upload_channel_id,
            upload_channel_name,
            upload_channel_handle,
            language,
            seed_sample_topics,
        } = await req.json()
        const categoryLanguage = normalizeContentLanguage(language)

        if (!name) {
            return NextResponse.json({ error: 'Name is required' }, { status: 400 })
        }
        if (RETIRED_CATEGORY_NAMES.has(String(name).trim())) {
            return NextResponse.json({ error: 'This category has been permanently retired' }, { status: 400 })
        }

        const fallbackEmail = requester.user?.email || SUPER_ADMIN_EMAIL || 'ejsh0519@naver.com'
        const effectiveEmail = assigned_employee_email || fallbackEmail

        const supabase = getAdmin()

        const categoryPayload: any = {
            name,
            keywords: keywords || '',
            benchmark_channel_url: benchmark_channel_url || '',
            assigned_employee_email: effectiveEmail,
            default_script_style: default_script_style || 'default',
            default_image_style: default_image_style || 'realistic',
            upload_channel_id: upload_channel_id || null,
            upload_channel_name: upload_channel_name || '',
            upload_channel_handle: upload_channel_handle || '',
            language: categoryLanguage,
        }

        let { data, error } = await supabase
            .from('categories')
            .insert([categoryPayload])
            .select()

        if (isMissingColumnError(error)) {
            const { language: _lang, upload_channel_id: _ucid, upload_channel_name: _ucname, upload_channel_handle: _uchandle, ...minimalPayload } = categoryPayload
            const retry = await supabase
                .from('categories')
                .insert([minimalPayload])
                .select()
            data = retry.data
            error = retry.error
        }

        if (error) throw error
        const createdCategory = data?.[0]
        if (!createdCategory) throw new Error('Category creation returned no row')

        const shouldSeedSampleTopics = Boolean(seed_sample_topics)
        if (shouldSeedSampleTopics) {
            const categoryId = createdCategory.id
            const fallbackKeyword = keywords || (categoryLanguage === 'en' ? 'latest trends' : categoryLanguage === 'ja' ? '最新トレンド' : '최신 트렌드')
            const sampleTopics = categoryLanguage === 'en'
                ? [
                    `[${name}] First recommended topic about ${fallbackKeyword}`,
                    `[${name}] Second recommended topic about ${fallbackKeyword}`,
                    `[${name}] Core target analysis based on benchmark channels`
                ]
                : categoryLanguage === 'ja'
                ? [
                    `[${name}] ${fallbackKeyword}に関するおすすめトピック 1`,
                    `[${name}] ${fallbackKeyword}に関するおすすめトピック 2`,
                    `[${name}] ベンチマークチャンネル分析に基づく主要ターゲット分析`
                ]
                : [
                    `[${name}] ${fallbackKeyword} 관련 첫 번째 추천 주제`,
                    `[${name}] ${fallbackKeyword} 관련 두 번째 추천 주제`,
                    `[${name}] 벤치마킹 채널 분석 기반 핵심 타겟 분석`
                ]
            
            const queueInserts = sampleTopics.map(topic => ({
                category_id: categoryId,
                topic,
                assigned_employee_email: effectiveEmail,
                assigned_script_style: default_script_style || 'default',
                language: categoryLanguage,
                status: 'pending'
            }))

            try {
                let { error: queueInsertError } = await supabase.from('topics_queue').insert(queueInserts)
                if (isMissingColumnError(queueInsertError)) {
                    const fallbackInserts = queueInserts.map(({ assigned_script_style, language: _language, ...rest }) => rest)
                    await supabase.from('topics_queue').insert(fallbackInserts)
                }
            } catch (qErr) {
                console.warn('Failed to seed sample topics:', qErr)
            }
        }

        await deleteServerCache(CATEGORIES_CACHE_KEY)
        return NextResponse.json({ success: true, category: createdCategory })
    } catch (e: any) {
        console.error('Failed to create category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 카테고리 삭제
export async function DELETE(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        if (!id) return NextResponse.json({ error: 'Missing category id' }, { status: 400 })

        const supabase = getAdmin()
        const { error } = await supabase
            .from('categories')
            .delete()
            .eq('id', id)

        if (error) throw error

        await deleteServerCache(CATEGORIES_CACHE_KEY)
        return NextResponse.json({ success: true })
    } catch (e: any) {
        console.error('Failed to delete category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PUT: 카테고리 수정
export async function PUT(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const {
            id,
            name,
            keywords,
            benchmark_channel_url,
            assigned_employee_email,
            default_script_style,
            default_image_style,
            upload_channel_id,
            upload_channel_name,
            upload_channel_handle,
            language,
        } = body
        const categoryLanguage = language !== undefined ? normalizeContentLanguage(language) : undefined

        if (!id) {
            return NextResponse.json({ error: 'Category ID is required' }, { status: 400 })
        }
        if (RETIRED_CATEGORY_IDS.has(Number(id))) {
            return NextResponse.json({ error: 'This category has been permanently retired' }, { status: 410 })
        }
        if (name !== undefined && RETIRED_CATEGORY_NAMES.has(String(name).trim())) {
            return NextResponse.json({ error: 'This category has been permanently retired' }, { status: 400 })
        }

        const supabase = getAdmin()

        const updateData: any = {}
        if (name !== undefined) updateData.name = name
        if (keywords !== undefined) updateData.keywords = keywords
        if (benchmark_channel_url !== undefined) updateData.benchmark_channel_url = benchmark_channel_url
        if (assigned_employee_email !== undefined && assigned_employee_email !== null) {
            updateData.assigned_employee_email = assigned_employee_email
        }
        if (default_script_style !== undefined) updateData.default_script_style = default_script_style
        if (default_image_style !== undefined) updateData.default_image_style = default_image_style
        if (upload_channel_id !== undefined) updateData.upload_channel_id = upload_channel_id || null
        if (upload_channel_name !== undefined) updateData.upload_channel_name = upload_channel_name || ''
        if (upload_channel_handle !== undefined) updateData.upload_channel_handle = upload_channel_handle || ''
        if (categoryLanguage !== undefined) updateData.language = categoryLanguage

        let { data, error } = await supabase
            .from('categories')
            .update(updateData)
            .eq('id', id)
            .select()

        if (isMissingColumnError(error)) {
            const { upload_channel_id: _ucid, upload_channel_name: _ucname, upload_channel_handle: _uchandle, language: _lang, ...fallbackUpdate } = updateData
            const retry = await supabase
                .from('categories')
                .update(fallbackUpdate)
                .eq('id', id)
                .select()
            data = retry.data
            error = retry.error
        }

        if (error) throw error
        const updatedCategory = data?.[0]
        if (!updatedCategory) throw new Error('Category update returned no row')

        // 언어가 변경된 경우 대기 중인 토픽들의 언어도 안전하게 동기화
        if (categoryLanguage !== undefined) {
            try {
                await supabase
                    .from('topics_queue')
                    .update({ language: categoryLanguage, assigned_employee_email: null })
                    .eq('category_id', id)
                    .in('status', ['pending', 'assigned'])
            } catch (queueErr) {
                console.warn('Failed to propagate category queue language update:', queueErr)
            }
        }

        await deleteServerCache(CATEGORIES_CACHE_KEY)
        return NextResponse.json({ success: true, category: updatedCategory })
    } catch (e: any) {
        console.error('Failed to update category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
