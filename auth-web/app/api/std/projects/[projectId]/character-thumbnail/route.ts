import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { charactersFromPayload } from '@/lib/stdCharacterProtection'

export const dynamic = 'force-dynamic'

function transformedSupabaseUrl(value: unknown): string {
    const raw = String(value || '').trim()
    if (!/^https:\/\//i.test(raw) || !raw.includes('.supabase.co/storage/v1/object/public/')) return ''
    const url = new URL(raw.replace('/storage/v1/object/public/', '/storage/v1/render/image/public/'))
    url.searchParams.set('width', '64')
    url.searchParams.set('height', '64')
    url.searchParams.set('resize', 'cover')
    url.searchParams.set('quality', '35')
    return url.toString()
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const requestUrl = new URL(req.url)
    const slot = Number(requestUrl.searchParams.get('slot'))
    if (!Number.isInteger(slot) || slot < 0 || slot > 20) {
        return NextResponse.json({ success: false, error: 'Invalid character slot' }, { status: 400 })
    }

    let query = supabaseAdmin.from('std_projects').select('project_payload').eq('id', params.projectId)
    if (auth.requester.email && !auth.requester.email.startsWith('admin') && !auth.requester.email.startsWith('worker')) {
        query = query.eq('employee_email', auth.requester.email)
    }
    const { data: project, error } = await query.maybeSingle()
    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const character = charactersFromPayload(project.project_payload)[slot]
    const thumbnailUrl = transformedSupabaseUrl(character?.image_url)
    if (!thumbnailUrl) return new NextResponse(null, { status: 404 })

    const upstream = await fetch(thumbnailUrl, { cache: 'force-cache' })
    if (!upstream.ok || !upstream.body) return new NextResponse(null, { status: 502 })
    return new NextResponse(upstream.body, {
        headers: {
            'Content-Type': upstream.headers.get('content-type') || 'image/webp',
            'Cache-Control': 'private, max-age=86400, stale-while-revalidate=604800',
            'Content-Disposition': 'inline',
            'X-Content-Type-Options': 'nosniff',
        },
    })
}
