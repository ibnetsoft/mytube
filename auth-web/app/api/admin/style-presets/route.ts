import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../_auth'
import { deleteServerCache, getServerCache, setServerCache } from '@/lib/server-cache'

export const dynamic = 'force-dynamic'
const STYLE_PRESETS_CACHE_TTL_SECONDS = 300

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const WEB_ADMIN_STYLE_TYPES = new Set(['script', 'thumbnail'])

// GET: 스타일 프리셋 목록 조회
export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const type = searchParams.get('type') // optional filter: 'image' | 'script' | 'thumbnail'
        const cacheKey = `admin:style-presets:${type || 'web'}`

        const cached = await getServerCache<{ presets: any[] }>(cacheKey)
        if (cached) {
            return NextResponse.json(cached, {
                headers: {
                    'Cache-Control': `private, max-age=${STYLE_PRESETS_CACHE_TTL_SECONDS}`,
                    'X-Admin-Cache': 'HIT',
                },
            })
        }

        const supabase = getAdmin()
        let query = supabase.from('style_presets').select('*').order('created_at', { ascending: false })
        
        if (type) {
            if (!WEB_ADMIN_STYLE_TYPES.has(type)) {
                return NextResponse.json({ presets: [] })
            }
            query = query.eq('preset_type', type)
        } else {
            query = query.in('preset_type', Array.from(WEB_ADMIN_STYLE_TYPES))
        }

        const { data, error } = await query

        if (error) throw error

        const response = { presets: data || [] }
        await setServerCache(cacheKey, response, STYLE_PRESETS_CACHE_TTL_SECONDS)

        return NextResponse.json(response, {
            headers: {
                'Cache-Control': `private, max-age=${STYLE_PRESETS_CACHE_TTL_SECONDS}`,
                'X-Admin-Cache': 'MISS',
            },
        })
    } catch (e: any) {
        console.error('Failed to get style presets:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// POST: 스타일 프리셋 추가/수정 (key_code 기준 upsert)
export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const { id, preset_type, key_code, display_name_ko, display_name_vi, prompt_template, gemini_instruction, image_url } = body

        if (!preset_type || !key_code || !display_name_ko || !prompt_template) {
            return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
        }
        if (!WEB_ADMIN_STYLE_TYPES.has(preset_type)) {
            return NextResponse.json({ error: 'Image style presets are Worker-managed' }, { status: 400 })
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

        await deleteServerCache('admin:style-presets:web')
        await deleteServerCache(`admin:style-presets:${preset_type}`)
        return NextResponse.json({ success: true, preset: data?.[0] })
    } catch (e: any) {
        console.error('Failed to save style preset:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 스타일 프리셋 삭제
export async function DELETE(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        const keyCode = searchParams.get('key_code')

        if (!id && !keyCode) {
            return NextResponse.json({ error: 'Missing style preset id or key_code' }, { status: 400 })
        }

        const supabase = getAdmin()
        let lookup = supabase.from('style_presets').select('id,preset_type')
        if (id) {
            lookup = lookup.eq('id', id)
        } else if (keyCode) {
            lookup = lookup.eq('key_code', keyCode)
        }
        const { data: existingRows, error: lookupError } = await lookup.limit(1)
        if (lookupError) throw lookupError
        const existing = existingRows?.[0]
        if (existing?.preset_type === 'image') {
            return NextResponse.json({ error: 'Image style presets are Worker-managed' }, { status: 400 })
        }

        let query = supabase.from('style_presets').delete()

        if (id) {
            query = query.eq('id', id)
        } else if (keyCode) {
            query = query.eq('key_code', keyCode)
        }

        const { error } = await query

        if (error) throw error

        await deleteServerCache('admin:style-presets:web')
        await deleteServerCache('admin:style-presets:script')
        await deleteServerCache('admin:style-presets:thumbnail')
        return NextResponse.json({ success: true })
    } catch (e: any) {
        console.error('Failed to delete style preset:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
