import { randomUUID } from 'node:crypto'
import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { buildStdGcsObjectPath, createGcsSignedUploadUrl, getGcsObjectMetadata } from '@/lib/gcsStorage'
import { assetContentIdentity } from '@/lib/stdContentIdentity'
import { validWuxiaClip, wuxiaClipStates, WUXIA_CLIP } from '@/lib/stdWuxiaClips'

export const dynamic = 'force-dynamic'
export const maxDuration = 60
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i

async function context(req: Request, projectId: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const { data: project, error } = await supabaseAdmin.rpc('std_user_web_project', { p_id: projectId })
    if (error) return { response: NextResponse.json({ error: '프로젝트를 불러오지 못했습니다.' }, { status: 503 }) }
    if (!project || String(project.employee_email).toLowerCase() !== auth.requester.email.toLowerCase())
        return { response: NextResponse.json({ error: '프로젝트를 찾을 수 없습니다.' }, { status: 404 }) }
    if (['approved', 'canceled', 'review_requested'].includes(project.status))
        return { response: NextResponse.json({ error: '편집 가능한 상태로 프로젝트를 다시 연 뒤 영상을 연결해 주세요.' }, { status: 409 }) }
    if (!wuxiaClipStates(project).length)
        return { response: NextResponse.json({ error: '무협 상태 원화가 없습니다.' }, { status: 422 }) }
    return { project }
}
async function touch(projectId: string) {
    const { error } = await supabaseAdmin.from('std_projects').update({ updated_at: new Date().toISOString() }).eq('id', projectId)
    if (error) throw Error('저장 상태를 갱신하지 못했습니다. 다시 연결해 주세요.')
}
export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const ctx = await context(req, params.projectId)
    if (ctx.response) return ctx.response
    try {
        const body = await req.json(), project = ctx.project
        const state = wuxiaClipStates(project).find(s => s.asset_id === body.state_asset_id)
        const mime = String(body.mime_type || '')
        if (!state || state.sha256 !== body.source_state_sha256 || mime !== 'video/mp4'
            || !Number.isInteger(body.file_size) || body.file_size <= 0 || body.file_size > 250 * 1024 * 1024)
            return NextResponse.json({ error: '원화 연결 또는 영상 파일 정보를 확인해 주세요.' }, { status: 422 })
        const id = randomUUID(), fileName = `${id}.mp4`
        const path = buildStdGcsObjectPath({ projectId: project.id, sceneNumber: state.scene_number, fileName })
        const signed = await createGcsSignedUploadUrl({ objectPath: path, contentType: mime, expiresInMinutes: 30 })
        const clip = { contract: WUXIA_CLIP, asset_id: id, state_asset_id: state.asset_id, source_state_sha256: state.sha256,
            sha256: body.sha256, gcs_bucket: signed.bucket, gcs_path: path, width: body.width, height: body.height,
            duration_seconds: body.duration_seconds, source_in_seconds: body.source_in_seconds,
            play_seconds: body.play_seconds, start_offset_seconds: body.start_offset_seconds }
        if (!validWuxiaClip(clip)) return NextResponse.json({ error: '16:9 영상과 정상 속도의 사용 구간을 확인해 주세요. 최대 원본 길이는 30초입니다.' }, { status: 422 })
        const planned = (project.project_payload?.structure?.scenes || []).find((s: any, i: number) => Number(s.scene_number || i + 1) === state.scene_number)
        const { error } = await supabaseAdmin.from('std_project_assets').insert({ id, project_id: project.id, scene_number: state.scene_number,
            asset_type: 'other', status: 'uploaded', file_name: fileName, mime_type: mime, file_size: body.file_size,
            metadata: { kind: 'wuxia_state_clip', ready: false, enabled: true, clip, gcs_bucket: signed.bucket, gcs_path: path,
                storage_provider: 'gcs', expected_size: body.file_size, content_identity: assetContentIdentity(project, { type: 'video', scene: planned }) } })
        if (error) throw Error('영상 업로드 준비를 저장하지 못했습니다.')
        return NextResponse.json({ success: true, asset_id: id, upload_url: signed.signedUrl })
    } catch (error: any) {
        return NextResponse.json({ error: error.message || '영상 업로드 준비 실패' }, { status: 503 })
    }
}
export async function PATCH(req: Request, { params }: { params: { projectId: string } }) {
    const ctx = await context(req, params.projectId)
    if (ctx.response) return ctx.response
    try {
        const body = await req.json()
        if (!UUID.test(body.asset_id || '') || !['complete', 'disable'].includes(body.action))
            return NextResponse.json({ error: '잘못된 영상 연결 요청입니다.' }, { status: 400 })
        const { data: asset, error } = await supabaseAdmin.from('std_project_assets').select('id,metadata,mime_type,status')
            .eq('id', body.asset_id).eq('project_id', params.projectId).maybeSingle()
        if (error) throw Error('영상 연결 정보를 불러오지 못했습니다.')
        const meta = asset?.metadata, clip = meta?.clip
        if (!asset || meta?.kind !== 'wuxia_state_clip' || (body.action === 'complete' && !validWuxiaClip(clip)))
            return NextResponse.json({ error: '영상 연결을 찾을 수 없습니다.' }, { status: 404 })
        const state = wuxiaClipStates(ctx.project).find(s => s.asset_id === clip.state_asset_id && s.sha256 === clip.source_state_sha256)
        if (!state && body.action === 'complete') return NextResponse.json({ error: '원화가 바뀌었습니다. 현재 원화를 기준으로 다시 준비해 주세요.' }, { status: 409 })
        if (body.action === 'complete') {
            const stored = await getGcsObjectMetadata({ bucket: clip.gcs_bucket, objectPath: clip.gcs_path })
            if (stored.size !== meta.expected_size || stored.contentType !== asset.mime_type)
                return NextResponse.json({ error: '영상 업로드가 끝나지 않았거나 파일 정보가 다릅니다.' }, { status: 422 })
        }
        const { error: saveError } = await supabaseAdmin.from('std_project_assets').update({
            metadata: { ...meta, ready: true, enabled: body.action === 'complete' }, updated_at: new Date().toISOString(),
        }).eq('id', asset.id).eq('project_id', params.projectId)
        if (saveError) throw Error('영상 연결을 저장하지 못했습니다.')
        await touch(params.projectId)
        return NextResponse.json({ success: true })
    } catch (error: any) {
        return NextResponse.json({ error: error.message || '영상 연결 저장 실패' }, { status: 503 })
    }
}
