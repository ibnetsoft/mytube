import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { audioAssetRole } from '@/lib/stdAudioMix'
export const dynamic = 'force-dynamic'

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    const { data: projects, error } = await supabaseAdmin.from('std_projects').select('id,status').eq('employee_email', auth.requester.email)
    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    const project = projects?.find(p => p.id === params.projectId)
    if (!project) return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    const { data: rows, error: assetError } = await supabaseAdmin.from('std_project_assets').select('*')
        .in('project_id', projects!.map(p => p.id)).in('status', ['uploaded', 'assigned'])
        .or('asset_type.eq.bgm,metadata->>audio_role.eq.bgm').order('created_at', { ascending: false })
    if (assetError) return NextResponse.json({ error: assetError.message }, { status: 500 })
    const sounds = (rows || []).filter(a => audioAssetRole(a) === 'bgm')
    let body: any
    try { body = await req.json() } catch { body = {} }
    if (!body.asset_id) {
        const seen = new Set<string>()
        const catalog = [...sounds.filter(a => a.project_id === project.id), ...sounds.filter(a => a.project_id !== project.id)].filter(a => {
            const key = a.metadata?.gcs_path || a.metadata?.storage_path || a.id
            if (seen.has(key)) return false
            seen.add(key); return true
        })
        return NextResponse.json({ assets: catalog }, { headers: { 'Cache-Control': 'no-store' } })
    }
    const source = sounds.find(a => a.id === body.asset_id)
    if (!source || project.status === 'canceled') return NextResponse.json({ error: 'Sound not available' }, { status: 404 })
    if (source.project_id === project.id) return NextResponse.json({ asset: source })
    const existing = sounds.find(a => a.project_id === project.id && (
        a.metadata?.bgm_source_asset_id === source.id || (source.metadata?.storage_path && a.metadata?.storage_path === source.metadata.storage_path) || (source.metadata?.gcs_path && a.metadata?.gcs_path === source.metadata.gcs_path)))
    if (existing) return NextResponse.json({ asset: existing })
    const { data: asset, error: saveError } = await supabaseAdmin.from('std_project_assets').insert({
        project_id: project.id, asset_type: 'other', status: 'uploaded', file_name: source.file_name,
        mime_type: source.mime_type, file_size: source.file_size,
        metadata: { ...source.metadata, audio_role: 'bgm', bgm_source_asset_id: source.id },
    }).select('*').single()
    if (saveError) return NextResponse.json({ error: saveError.message }, { status: 500 })
    return NextResponse.json({ asset })
}
