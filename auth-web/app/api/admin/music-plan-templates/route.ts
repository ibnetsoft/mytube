import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
  { auth: { persistSession: false } }
)

export async function GET() {
  try {
    const supabase = getAdmin()
    const { data, error } = await supabase
      .from('style_presets')
      .select('*')
      .eq('preset_type', 'music_plan')
      .order('created_at', { ascending: false })

    if (error) throw error
    return NextResponse.json({ success: true, templates: data || [] })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const {
      id,
      key_code,
      display_name_ko,
      display_name_vi,
      prompt_template,
      gemini_instruction,
      image_url,
    } = body || {}

    if (!key_code || !display_name_ko || !prompt_template) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
    }

    const payload: Record<string, any> = {
      preset_type: 'music_plan',
      key_code,
      display_name_ko,
      display_name_vi: display_name_vi || '',
      prompt_template,
      gemini_instruction: gemini_instruction || '',
      image_url: image_url || '',
    }
    if (id) payload.id = id

    const supabase = getAdmin()
    const { data, error } = await supabase
      .from('style_presets')
      .upsert(payload, { onConflict: 'key_code' })
      .select()

    if (error) throw error
    return NextResponse.json({ success: true, template: data?.[0] || null })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}

export async function DELETE(req: Request) {
  try {
    const { searchParams } = new URL(req.url)
    const id = searchParams.get('id')
    const keyCode = searchParams.get('key_code')
    if (!id && !keyCode) {
      return NextResponse.json({ error: 'Missing id or key_code' }, { status: 400 })
    }

    const supabase = getAdmin()
    let query = supabase.from('style_presets').delete().eq('preset_type', 'music_plan')
    if (id) {
      query = query.eq('id', id)
    } else {
      query = query.eq('key_code', keyCode)
    }

    const { error } = await query
    if (error) throw error
    return NextResponse.json({ success: true })
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
