import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: 스타일 프리셋 목록 조회
export async function GET(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const type = searchParams.get('type') // optional filter: 'image' | 'script' | 'thumbnail'

        const supabase = getAdmin()
        let query = supabase.from('style_presets').select('*').order('created_at', { ascending: false })
        
        if (type) {
            query = query.eq('preset_type', type)
        }

        const { data, error } = await query

        if (error) throw error

        return NextResponse.json({ presets: data || [] })
    } catch (e: any) {
        console.error('Failed to get style presets:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// POST: 스타일 프리셋 추가/수정 (key_code 기준 upsert)
export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { id, preset_type, key_code, display_name_ko, display_name_vi, prompt_template, gemini_instruction, image_url } = body

        if (!preset_type || !key_code || !display_name_ko || !prompt_template) {
            return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
        }

        const supabase = getAdmin()

        // Upsert by key_code
        const payload: any = {
            preset_type,
            key_code,
            display_name_ko,
            display_name_vi: display_name_vi || '',
            prompt_template,
            gemini_instruction: gemini_instruction || '',
            image_url: image_url || ''
        }

        if (id) {
            payload.id = id
        }

        const { data, error } = await supabase
            .from('style_presets')
            .upsert(payload, { onConflict: 'key_code' })
            .select()

        if (error) throw error

        return NextResponse.json({ success: true, preset: data?.[0] })
    } catch (e: any) {
        console.error('Failed to save style preset:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 스타일 프리셋 삭제
export async function DELETE(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        const keyCode = searchParams.get('key_code')

        if (!id && !keyCode) {
            return NextResponse.json({ error: 'Missing style preset id or key_code' }, { status: 400 })
        }

        const supabase = getAdmin()
        let query = supabase.from('style_presets').delete()

        if (id) {
            query = query.eq('id', id)
        } else if (keyCode) {
            query = query.eq('key_code', keyCode)
        }

        const { error } = await query

        if (error) throw error

        return NextResponse.json({ success: true })
    } catch (e: any) {
        console.error('Failed to delete style preset:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
