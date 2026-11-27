import { createHash, randomUUID } from 'node:crypto'
import { NextResponse } from 'next/server'
import sharp from 'sharp'
import { uploadGcsBuffer } from '@/lib/gcsStorage'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
const MAX_FILE_BYTES = 4 * 1024 * 1024

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    try {
        const form = await req.formData()
        const image = form.get('file')
        const number = Number(form.get('scene_number'))
        if (!(image instanceof File) || !['image/png', 'image/jpeg', 'image/webp'].includes(image.type) || image.size < 1 || image.size > MAX_FILE_BYTES
            || !Number.isSafeInteger(number) || number < 1) {
            return NextResponse.json({ error: '4MB 이하의 이미지와 씬 번호를 확인해 주세요.' }, { status: 400 })
        }
        const { data: project, error: projectError } = await supabaseAdmin.from('std_projects')
            .select('id,user_id,employee_email,status,submitted_at,updated_at,project_style:project_payload->>image_style,structure_style:project_payload->structure->>image_style,setting_style:project_payload->structure->effective_user_settings->>image_style,package_contract:project_payload->structure->wuxia_ae_package->>contract,strict_identity:project_payload->>strict_content_identity')
            .eq('id', params.projectId).eq('employee_email', auth.requester.email).maybeSingle()
        if (projectError) throw projectError
        if (!project || project.user_id !== auth.requester.user.id) return NextResponse.json({ error: '프로젝트를 찾을 수 없습니다.' }, { status: 404 })
        const wuxia = project.package_contract === 'wuxia_still_ae_episode/v1' || (project.structure_style || project.project_style || project.setting_style) === 'wuxia_webtoon'
        if (!['claimed', 'in_progress'].includes(project.status) || project.submitted_at || !wuxia) {
            return NextResponse.json({ error: '편집 가능한 무협 프로젝트에서 요청해 주세요.' }, { status: 409 })
        }
        if (project.strict_identity === 'true' || project.package_contract) {
            return NextResponse.json({ error: '이 프로젝트의 원본 패키지는 별도 재검토가 필요합니다. 기존 이미지는 유지됩니다.' }, { status: 409 })
        }
        const { data: scene, error: sceneError } = await supabaseAdmin.from('std_project_scenes')
            .select('id,scene_number,updated_at,metadata').eq('project_id', project.id).eq('scene_number', number).maybeSingle()
        if (sceneError) throw sceneError
        const sourceSha = String(scene?.metadata?.source_image_sha256 || '')
        if (!scene || !/^[a-f0-9]{64}$/.test(sourceSha) || !scene.metadata?.cut_id) {
            return NextResponse.json({ error: '현재 씬의 원본과 컷 연결을 확인할 수 없습니다.' }, { status: 409 })
        }
        const { data: videos, error: videoError } = await supabaseAdmin.from('std_project_assets')
            .select('id,metadata').eq('project_id', project.id).eq('scene_number', number).eq('asset_type', 'video')
            .in('status', ['uploaded', 'assigned']).limit(100)
        if (videoError) throw videoError
        if ((videos || []).some((video: any) => !video.metadata?.ae_mouth_fingerprint && !video.metadata?.lipsync_fingerprint && video.metadata?.kind !== 'mouth_preview')) {
            return NextResponse.json({ error: '원본 영상이 연결된 씬입니다. 기존 영상과 이미지를 유지합니다.' }, { status: 409 })
        }
        const { data: active, error: activeError } = await supabaseAdmin.from('std_scene_image_reviews').select('id')
            .eq('project_id', project.id).eq('scene_id', scene.id).in('status', ['queued', 'running']).limit(1)
        if (activeError) throw activeError
        if (active?.length) return NextResponse.json({ error: '이 씬의 이미지 검수가 이미 진행 중입니다.' }, { status: 409 })
        const raw = Buffer.from(await image.arrayBuffer())
        const candidate = await sharp(raw, { limitInputPixels: 16_000_000 }).rotate().png().toBuffer()
        const sha = createHash('sha256').update(candidate).digest('hex')
        if (sha === sourceSha) return NextResponse.json({ error: '현재 이미지와 같은 파일입니다.' }, { status: 409 })
        const id = randomUUID()
        const path = `std-projects/${project.id}/scene-image-review/${id}/${sha}.png`
        const stored = await uploadGcsBuffer({ objectPath: path, data: candidate, contentType: 'image/png' })
        const { data, error } = await supabaseAdmin.from('std_scene_image_reviews').insert({
            id, project_id: project.id, scene_id: scene.id, scene_number: number,
            owner_id: project.user_id, owner_email: auth.requester.email, source_sha256: sourceSha,
            candidate_sha256: sha, candidate_bucket: stored.bucket, candidate_path: stored.path,
            project_updated_at: project.updated_at, scene_updated_at: scene.updated_at,
        }).select('id,status').single()
        if (error?.code === '23505') return NextResponse.json({ error: '이 씬의 이미지 검수가 이미 진행 중입니다.' }, { status: 409 })
        if (error) throw error
        return NextResponse.json({ success: true, review: data })
    } catch (error: any) {
        console.error('[scene-image-review] enqueue failed', error?.message)
        return NextResponse.json({ error: '이미지 검수 요청을 저장하지 못했습니다. 기존 이미지는 유지됩니다.' }, { status: 503 })
    }
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    const { data, error } = await supabaseAdmin.from('std_scene_image_reviews')
        .select('id,scene_number,status,error,created_at,updated_at')
        .eq('project_id', params.projectId).eq('owner_id', auth.requester.user.id)
        .order('created_at', { ascending: false }).limit(200)
    if (error) return NextResponse.json({ error: '이미지 검수 상태를 불러오지 못했습니다.' }, { status: 503 })
    return NextResponse.json({ success: true, reviews: data })
}
