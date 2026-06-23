import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin, requireSuperAdmin } from '../_auth'

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

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('categories')
            .select('*')
            .order('created_at', { ascending: false })

        if (error) throw error

        return NextResponse.json({
            categories: (data || []).map((category: any) => ({
                ...category,
                language: normalizeContentLanguage(category.language),
            }))
        })
    } catch (e: any) {
        console.error('Failed to get categories:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const {
            name,
            keywords,
            benchmark_channel_url,
            assigned_employee_email,
            default_script_style,
            default_image_style,
            video_type,
            upload_channel_id,
            upload_channel_name,
            upload_channel_handle,
            language,
        } = await req.json()
        const categoryLanguage = normalizeContentLanguage(language)

        if (!name) {
            return NextResponse.json({ error: 'Name is required' }, { status: 400 })
        }

        const supabase = getAdmin()

        const categoryPayload = {
            name,
            keywords: keywords || '',
            benchmark_channel_url: benchmark_channel_url || '',
            assigned_employee_email: assigned_employee_email || null,
            default_script_style: default_script_style || 'default',
            default_image_style: default_image_style || 'realistic',
            video_type: video_type || 'longform',
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
            const { language: _language, ...fallbackPayload } = categoryPayload
            const retry = await supabase
                .from('categories')
                .insert([fallbackPayload])
                .select()
            data = retry.data
            error = retry.error
        }

        if (error) throw error
        const createdCategory = data?.[0]
        if (!createdCategory) throw new Error('Category creation returned no row')

        // 카테고리 생성 성공 시 임시 트리거: AI 주제 생성을 모방하여 큐에 즉시 샘플 주제 3개 적재 (또는 배치 스케줄러가 나중에 채움)
        // 일단 UI 연동 및 빠른 테스트를 위해 카테고리 추가 시 기본 샘플 주제 3개를 큐에 넣어둡니다.
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
            assigned_employee_email: assigned_employee_email || null,
            assigned_script_style: default_script_style || 'default',
            assigned_image_style: default_image_style || 'realistic',
            language: categoryLanguage,
            status: 'pending'
        }))

        let { error: queueInsertError } = await supabase.from('topics_queue').insert(queueInserts)
        if (isMissingColumnError(queueInsertError)) {
            const fallbackInserts = queueInserts.map(({ assigned_script_style, assigned_image_style, language: _language, ...rest }) => rest)
            const retry = await supabase.from('topics_queue').insert(fallbackInserts)
            queueInsertError = retry.error
        }
        if (queueInsertError) throw queueInsertError

        return NextResponse.json({ success: true, category: createdCategory })
    } catch (e: any) {
        console.error('Failed to create category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 카테고리 삭제
export async function DELETE(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
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

        return NextResponse.json({ success: true })
    } catch (e: any) {
        console.error('Failed to delete category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PUT: 카테고리 수정
export async function PUT(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
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
            video_type,
            upload_channel_id,
            upload_channel_name,
            upload_channel_handle,
            language,
        } = body
        const categoryLanguage = language !== undefined ? normalizeContentLanguage(language) : undefined

        if (!id) {
            return NextResponse.json({ error: 'Category ID is required' }, { status: 400 })
        }

        const supabase = getAdmin()

        const updateData: any = {}
        if (name !== undefined) updateData.name = name
        if (keywords !== undefined) updateData.keywords = keywords
        if (benchmark_channel_url !== undefined) updateData.benchmark_channel_url = benchmark_channel_url
        if (assigned_employee_email !== undefined) updateData.assigned_employee_email = assigned_employee_email || null
        if (default_script_style !== undefined) updateData.default_script_style = default_script_style
        if (default_image_style !== undefined) updateData.default_image_style = default_image_style
        if (video_type !== undefined) updateData.video_type = video_type
        if (upload_channel_id !== undefined) updateData.upload_channel_id = upload_channel_id || null
        if (upload_channel_name !== undefined) updateData.upload_channel_name = upload_channel_name || ''
        if (upload_channel_handle !== undefined) updateData.upload_channel_handle = upload_channel_handle || ''
        if (categoryLanguage !== undefined) updateData.language = categoryLanguage

        let { data, error } = await supabase
            .from('categories')
            .update(updateData)
            .eq('id', id)
            .select()

        if (isMissingColumnError(error) && updateData.language !== undefined) {
            const { language: _language, ...fallbackUpdate } = updateData
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

        // 언어가 바뀐 기존 미완료 토픽은 이전 담당자의 언어 지원 여부를 보장할 수 없으므로 미배정으로 돌립니다.
        // 담당자 변경만으로는 언어 매칭 배정을 덮어쓰지 않습니다. 새 담당자는 이후 생성되는 토픽에서 검증됩니다.
        const queueUpdate: any = {}
        if (categoryLanguage !== undefined) {
            queueUpdate.language = categoryLanguage
            queueUpdate.assigned_employee_email = null
        }
        if (Object.keys(queueUpdate).length > 0) {
            const { error: queueUpdateError } = await supabase
                .from('topics_queue')
                .update(queueUpdate)
                .eq('category_id', id)
                .in('status', ['pending', 'assigned'])
            if (isMissingColumnError(queueUpdateError) && queueUpdate.language !== undefined) {
                const { language: _language, ...fallbackQueueUpdate } = queueUpdate
                if (Object.keys(fallbackQueueUpdate).length > 0) {
                    await supabase
                        .from('topics_queue')
                        .update(fallbackQueueUpdate)
                        .eq('category_id', id)
                        .in('status', ['pending', 'assigned'])
                }
            } else if (queueUpdateError) {
                console.warn('Failed to propagate category queue fields:', queueUpdateError)
            }
        }

        return NextResponse.json({ success: true, category: updatedCategory })
    } catch (e: any) {
        console.error('Failed to update category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
