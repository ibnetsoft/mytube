import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { readSceneImage } from '@/lib/stdSceneImageDownload'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function safeAsciiFilename(value: string) {
    return String(value || 'scene-image')
        .normalize('NFKD')
        .replace(/[^\w.-]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '')
        .slice(0, 120) || 'scene-image'
}

function contentDisposition(filename: string) {
    const fallback = safeAsciiFilename(filename)
    return `attachment; filename="${fallback}"`
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const sceneNumber = Number(url.searchParams.get('sceneNumber') || url.searchParams.get('scene') || 0)
    if (!Number.isFinite(sceneNumber) || sceneNumber < 1) {
        return NextResponse.json({ success: false, error: 'sceneNumber is required' }, { status: 400 })
    }
    if (!UUID_RE.test(params.projectId)) {
        return NextResponse.json({ success: false, error: 'Invalid project id' }, { status: 400 })
    }

    let projectQuery = supabaseAdmin
        .from('std_projects')
        .select('id,title,project_payload')
        .eq('id', params.projectId)

    if (auth.requester.email && !auth.requester.email.startsWith('admin') && !auth.requester.email.startsWith('worker')) {
        projectQuery = projectQuery.eq('employee_email', auth.requester.email)
    }

    const { data: project, error: projectError } = await projectQuery.maybeSingle()
    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const { data: scene, error: sceneError } = await supabaseAdmin
        .from('std_project_scenes')
        .select('scene_number,scene_title,image_prompt,metadata')
        .eq('project_id', project.id)
        .eq('scene_number', sceneNumber)
        .maybeSingle()
    if (sceneError) return NextResponse.json({ success: false, error: sceneError.message }, { status: 500 })

    const payloadScenes = Array.isArray(project?.project_payload?.structure?.scenes)
        ? project.project_payload.structure.scenes
        : (Array.isArray(project?.project_payload?.scenes) ? project.project_payload.scenes : [])
    const payloadScene = payloadScenes.find((item: any, index: number) =>
        Number(item?.scene_number || item?.scene_order || index + 1) === sceneNumber
    )

    let image: Awaited<ReturnType<typeof readSceneImage>>
    try {
        image = await readSceneImage(req, scene, payloadScene)
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'Scene image fetch failed' }, { status: 502 })
    }
    const { buffer, contentType, extension: ext } = image
    const projectKey = String(project?.id || params.projectId).slice(0, 8) || 'project'
    const filename = `std-${projectKey}-scene-${String(sceneNumber).padStart(3, '0')}.${ext}`

    return new NextResponse(new Uint8Array(buffer), {
        headers: {
            'Content-Type': contentType,
            'Content-Length': String(buffer.byteLength),
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
            'Content-Disposition': contentDisposition(filename),
        },
    })
}
