import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function safeAsciiFilename(value: string, fallback = 'scene-images') {
    return String(value || fallback)
        .normalize('NFKD')
        .replace(/[^\w.-]+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '')
        .slice(0, 120) || fallback
}

function contentDisposition(filename: string) {
    const fallback = safeAsciiFilename(filename, 'scene-images.zip')
    return `attachment; filename="${fallback}"; filename*=UTF-8''${encodeURIComponent(filename)}`
}

function extractImageUrl(scene: any, payloadScene: any) {
    return String(
        scene?.image_url
        || scene?.image
        || scene?.metadata?.image_url
        || scene?.metadata?.image
        || payloadScene?.image_url
        || payloadScene?.image
        || ''
    ).trim()
}

function crc32(data: Uint8Array) {
    let crc = -1
    for (let i = 0; i < data.length; i += 1) {
        crc ^= data[i]
        for (let j = 0; j < 8; j += 1) {
            crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
        }
    }
    return (crc ^ -1) >>> 0
}

function dosDateTime(date = new Date()) {
    const year = Math.max(1980, date.getFullYear())
    const dosTime = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2)
    const dosDate = ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate()
    return { dosTime, dosDate }
}

function writeUInt16(target: Uint8Array, offset: number, value: number) {
    target[offset] = value & 0xff
    target[offset + 1] = (value >>> 8) & 0xff
}

function writeUInt32(target: Uint8Array, offset: number, value: number) {
    target[offset] = value & 0xff
    target[offset + 1] = (value >>> 8) & 0xff
    target[offset + 2] = (value >>> 16) & 0xff
    target[offset + 3] = (value >>> 24) & 0xff
}

function makeZip(files: Array<{ name: string, data: Uint8Array }>) {
    const encoder = new TextEncoder()
    const now = dosDateTime()
    const localParts: Uint8Array[] = []
    const centralParts: Uint8Array[] = []
    let offset = 0

    for (const file of files) {
        const nameBytes = encoder.encode(file.name)
        const checksum = crc32(file.data)

        const local = new Uint8Array(30 + nameBytes.length + file.data.length)
        writeUInt32(local, 0, 0x04034b50)
        writeUInt16(local, 4, 20)
        writeUInt16(local, 6, 0x0800)
        writeUInt16(local, 8, 0)
        writeUInt16(local, 10, now.dosTime)
        writeUInt16(local, 12, now.dosDate)
        writeUInt32(local, 14, checksum)
        writeUInt32(local, 18, file.data.length)
        writeUInt32(local, 22, file.data.length)
        writeUInt16(local, 26, nameBytes.length)
        writeUInt16(local, 28, 0)
        local.set(nameBytes, 30)
        local.set(file.data, 30 + nameBytes.length)
        localParts.push(local)

        const central = new Uint8Array(46 + nameBytes.length)
        writeUInt32(central, 0, 0x02014b50)
        writeUInt16(central, 4, 20)
        writeUInt16(central, 6, 20)
        writeUInt16(central, 8, 0x0800)
        writeUInt16(central, 10, 0)
        writeUInt16(central, 12, now.dosTime)
        writeUInt16(central, 14, now.dosDate)
        writeUInt32(central, 16, checksum)
        writeUInt32(central, 20, file.data.length)
        writeUInt32(central, 24, file.data.length)
        writeUInt16(central, 28, nameBytes.length)
        writeUInt16(central, 30, 0)
        writeUInt16(central, 32, 0)
        writeUInt16(central, 34, 0)
        writeUInt16(central, 36, 0)
        writeUInt32(central, 38, 0)
        writeUInt32(central, 42, offset)
        central.set(nameBytes, 46)
        centralParts.push(central)

        offset += local.length
    }

    const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0)
    const end = new Uint8Array(22)
    writeUInt32(end, 0, 0x06054b50)
    writeUInt16(end, 8, files.length)
    writeUInt16(end, 10, files.length)
    writeUInt32(end, 12, centralSize)
    writeUInt32(end, 16, offset)
    writeUInt16(end, 20, 0)

    const total = offset + centralSize + end.length
    const zip = new Uint8Array(total)
    let cursor = 0
    for (const part of [...localParts, ...centralParts, end]) {
        zip.set(part, cursor)
        cursor += part.length
    }
    return zip
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const requestedScenes = new Set(
        String(url.searchParams.get('scenes') || '')
            .split(',')
            .map(value => Number(value.trim()))
            .filter(value => Number.isFinite(value) && value > 0)
    )

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

    let scenesQuery = supabaseAdmin
        .from('std_project_scenes')
        .select('scene_number,scene_title,image_prompt,metadata')
        .eq('project_id', project.id)
        .order('scene_number', { ascending: true })
    if (requestedScenes.size > 0) {
        scenesQuery = scenesQuery.in('scene_number', Array.from(requestedScenes))
    }

    const { data: scenes, error: scenesError } = await scenesQuery
    if (scenesError) return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })

    const payloadScenes = Array.isArray(project?.project_payload?.structure?.scenes)
        ? project.project_payload.structure.scenes
        : (Array.isArray(project?.project_payload?.scenes) ? project.project_payload.scenes : [])

    const files: Array<{ name: string, data: Uint8Array }> = []
    for (const scene of scenes || []) {
        const sceneNumber = Number(scene?.scene_number || 0)
        const payloadScene = payloadScenes.find((item: any, index: number) =>
            Number(item?.scene_number || item?.scene_order || index + 1) === sceneNumber
        )
        const imageUrl = extractImageUrl(scene, payloadScene)
        if (!imageUrl) continue
        let response: Response
        try {
            response = await fetch(imageUrl)
        } catch {
            continue
        }
        if (!response.ok) continue
        const bytes = new Uint8Array(await response.arrayBuffer())
        const contentType = response.headers.get('content-type') || 'image/png'
        const ext = contentType.includes('webp') ? 'webp' : contentType.includes('jpeg') || contentType.includes('jpg') ? 'jpg' : 'png'
        files.push({
            name: `scene-${String(sceneNumber).padStart(3, '0')}.${ext}`,
            data: bytes,
        })
    }

    if (!files.length) {
        return NextResponse.json({ success: false, error: 'No scene images found' }, { status: 404 })
    }

    const title = String(project?.title || 'std-project').trim()
    const filename = `${title}-images.zip`
    const zip = makeZip(files)

    return new NextResponse(zip, {
        headers: {
            'Content-Type': 'application/zip',
            'Content-Length': String(zip.byteLength),
            'Cache-Control': 'private, max-age=300',
            'Content-Disposition': contentDisposition(filename),
        },
    })
}
