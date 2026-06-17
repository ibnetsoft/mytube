import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: 카테고리 목록 조회
export async function GET(req: Request) {
    try {
        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('categories')
            .select('*')
            .order('created_at', { ascending: false })

        if (error) throw error

        return NextResponse.json({ categories: data || [] })
    } catch (e: any) {
        console.error('Failed to get categories:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
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
        } = await req.json()

        if (!name || !assigned_employee_email) {
            return NextResponse.json({ error: 'Name and Employee email are required' }, { status: 400 })
        }

        const supabase = getAdmin()

        // 하나의 카테고리가 직원에게 정해지면 그 직원은 계속 그 카테고리만 작업할 수 있도록 독점 매핑 검증
        const { data: existingCat, error: checkError } = await supabase
            .from('categories')
            .select('name')
            .eq('assigned_employee_email', assigned_employee_email)
            .maybeSingle()

        if (checkError) throw checkError
        if (existingCat) {
            return NextResponse.json({ error: `이 직원은 이미 '${existingCat.name}' 카테고리에 배정되어 있습니다. 한 직원은 하나의 카테고리만 담당할 수 있습니다.` }, { status: 400 })
        }

        const { data, error } = await supabase
            .from('categories')
            .insert([{
                name,
                keywords: keywords || '',
                benchmark_channel_url: benchmark_channel_url || '',
                assigned_employee_email,
                default_script_style: default_script_style || 'default',
                default_image_style: default_image_style || 'realistic',
                video_type: video_type || 'longform',
                upload_channel_id: upload_channel_id || null,
                upload_channel_name: upload_channel_name || '',
                upload_channel_handle: upload_channel_handle || '',
            }])
            .select()

        if (error) throw error

        // 카테고리 생성 성공 시 임시 트리거: AI 주제 생성을 모방하여 큐에 즉시 샘플 주제 3개 적재 (또는 배치 스케줄러가 나중에 채움)
        // 일단 UI 연동 및 빠른 테스트를 위해 카테고리 추가 시 기본 샘플 주제 3개를 큐에 넣어둡니다.
        const categoryId = data[0].id
        const sampleTopics = [
            `[${name}] ${keywords || '최신 트렌드'} 관련 첫 번째 추천 주제`,
            `[${name}] ${keywords || '최신 트렌드'} 관련 두 번째 추천 주제`,
            `[${name}] 벤치마킹 채널 분석 기반 핵심 타겟 분석`
        ]
        
        const queueInserts = sampleTopics.map(topic => ({
            category_id: categoryId,
            topic,
            assigned_employee_email,
            status: 'pending'
        }))

        await supabase.from('topics_queue').insert(queueInserts)

        return NextResponse.json({ success: true, category: data[0] })
    } catch (e: any) {
        console.error('Failed to create category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 카테고리 삭제
export async function DELETE(req: Request) {
    try {
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
        } = body

        if (!id) {
            return NextResponse.json({ error: 'Category ID is required' }, { status: 400 })
        }

        const supabase = getAdmin()

        if (assigned_employee_email) {
            // 해당 이메일의 직원이 이미 다른 카테고리에 배정되어 있는지 확인 (현재 카테고리 제외)
            const { data: existingCat, error: checkError } = await supabase
                .from('categories')
                .select('id, name')
                .eq('assigned_employee_email', assigned_employee_email)
                .neq('id', id)
                .maybeSingle()

            if (checkError) throw checkError
            if (existingCat) {
                return NextResponse.json({ error: `이 직원은 이미 '${existingCat.name}' 카테고리에 배정되어 있습니다.` }, { status: 400 })
            }
        }

        const updateData: any = {}
        if (name !== undefined) updateData.name = name
        if (keywords !== undefined) updateData.keywords = keywords
        if (benchmark_channel_url !== undefined) updateData.benchmark_channel_url = benchmark_channel_url
        if (assigned_employee_email !== undefined) updateData.assigned_employee_email = assigned_employee_email
        if (default_script_style !== undefined) updateData.default_script_style = default_script_style
        if (default_image_style !== undefined) updateData.default_image_style = default_image_style
        if (video_type !== undefined) updateData.video_type = video_type
        if (upload_channel_id !== undefined) updateData.upload_channel_id = upload_channel_id || null
        if (upload_channel_name !== undefined) updateData.upload_channel_name = upload_channel_name || ''
        if (upload_channel_handle !== undefined) updateData.upload_channel_handle = upload_channel_handle || ''

        const { data, error } = await supabase
            .from('categories')
            .update(updateData)
            .eq('id', id)
            .select()

        if (error) throw error

        // 담당 직원이 바뀌면 아직 완료되지 않은 토픽들도 새로운 직원 이메일로 같이 업데이트해 줍니다.
        if (assigned_employee_email) {
            await supabase
                .from('topics_queue')
                .update({ assigned_employee_email })
                .eq('category_id', id)
                .in('status', ['pending', 'assigned'])
        }

        return NextResponse.json({ success: true, category: data[0] })
    } catch (e: any) {
        console.error('Failed to update category:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
