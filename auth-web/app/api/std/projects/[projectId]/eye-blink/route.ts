import { createHash } from 'crypto'
import { NextResponse } from 'next/server'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { coordinateSource } from '@/lib/stdSpeakerGeometry'
import { downloadGcsObject } from '@/lib/gcsStorage'

export const dynamic = 'force-dynamic'
type Box = [number, number, number, number]

const validBox = (box: any): box is Box =>
    Array.isArray(box) && box.length === 4 && box.every((v: any) => typeof v === 'number' && Number.isFinite(v)) &&
    0 <= box[0] && box[0] < box[2] && box[2] <= 1 && 0 <= box[1] && box[1] < box[3] && box[3] <= 1 &&
    box[2] - box[0] >= .005 && box[2] - box[0] <= .14 && box[3] - box[1] >= .004 && box[3] - box[1] <= .10

async function context(req: Request, id: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const project = await db.from('std_projects').select('*').eq('id', id).eq('employee_email', auth.requester.email).maybeSingle()
    if (project.error) throw project.error
    if (!project.data || project.data.status === 'canceled') return { response: NextResponse.json({ error: '프로젝트를 찾을 수 없습니다.' }, { status: 404 }) }
    const assets = await db.from('std_project_assets').select('*').eq('project_id', id).in('status', ['uploaded', 'assigned']).order('created_at', { ascending: false })
    if (assets.error) throw assets.error
    return { project: project.data, assets: assets.data || [] }
}

function sceneCharacters(project: any, number: number) {
    const structure = project.project_payload?.structure || {}
    const entry = (structure.scene_cast || []).find((row: any) => Number(row.scene_number) === number)
    return [...new Set<string>((entry?.characters || []).map((value: any) => String(value || '').trim()).filter(Boolean))]
}

function scenes(ctx: any) {
    const images = ctx.assets.filter((asset: any) => asset.asset_type === 'image' && Number(asset.scene_number) >= 19)
    const numbers = [...new Set<number>(images.map((asset: any) => Number(asset.scene_number)))].sort((a, b) => a - b)
    return numbers.map(number => {
        const image = images.find((asset: any) => Number(asset.scene_number) === number)
        const plan = ctx.assets.find((asset: any) => asset.metadata?.kind === 'eye_blink_confirmation' && Number(asset.scene_number) === number && asset.metadata.image_id === image.id)
        return { number, imageId: image.id, characters: sceneCharacters(ctx.project, number), plan: plan ? { id: plan.id, ...plan.metadata } : null }
    })
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const imageNumber = Number(new URL(req.url).searchParams.get('image') || 0)
        if (imageNumber) {
            const scene = scenes(ctx).find(row => row.number === imageNumber)
            const image = ctx.assets!.find((asset: any) => asset.id === scene?.imageId)
            if (!image) throw new Error('원본 이미지를 찾지 못했습니다.')
            const source = coordinateSource(image)
            const bytes = await downloadGcsObject({ bucket: source.bucket, objectPath: source.path })
            const sha = createHash('sha256').update(bytes).digest('hex')
            return new NextResponse(new Uint8Array(bytes), { headers: {
                'Content-Type': image.mime_type || 'image/png',
                'Cache-Control': 'private, no-store',
                'X-Air-Image-Sha256': sha,
            } })
        }
        return NextResponse.json({ scenes: scenes(ctx) }, { headers: { 'Cache-Control': 'private, no-store' } })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 400 })
    }
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const body = await req.json(), number = Number(body.sceneNumber)
        const scene = scenes(ctx).find(row => row.number === number)
        const image = ctx.assets!.find((asset: any) => asset.id === scene?.imageId)
        if (!scene || !image || body.imageId !== image.id) throw new Error('원본 이미지가 변경됐습니다. 다시 불러와 주세요.')
        const character = String(body.character || '').trim()
        if (character.length > 100) throw new Error('캐릭터 이름은 100자 이내로 입력해 주세요.')
        if (!validBox(body.leftEyeBox) || !validBox(body.rightEyeBox)) throw new Error('왼쪽 눈과 오른쪽 눈의 작은 영역을 각각 지정해 주세요.')
        const [left, right] = [body.leftEyeBox, body.rightEyeBox]
        if (left[0] < right[2] && left[2] > right[0] && left[1] < right[3] && left[3] > right[1]) throw new Error('왼쪽 눈과 오른쪽 눈 영역이 겹칠 수 없습니다.')
        const interval = Number(body.intervalSeconds)
        if (!Number.isFinite(interval) || interval < 2 || interval > 12) throw new Error('눈 깜빡임 간격은 2~12초로 설정해 주세요.')
        const source = coordinateSource(image)
        const bytes = await downloadGcsObject({ bucket: source.bucket, objectPath: source.path })
        const sha = createHash('sha256').update(bytes).digest('hex')
        if (body.imageSha256 && sha !== body.imageSha256) throw new Error('원본 이미지가 변경됐습니다. 다시 불러와 주세요.')
        const metadata = { kind: 'eye_blink_confirmation', version: 1, state: 'confirmed', scene_number: number,
            image_id: image.id, source_bucket: source.bucket, source_path: source.path, source_sha256: sha,
            character: character || null, left_eye_box: [...left], right_eye_box: [...right], interval_seconds: interval,
            confirmed_by: 'user', confirmed_at: new Date().toISOString() }
        const inserted = await db.from('std_project_assets').insert({ project_id: params.projectId, scene_number: number,
            asset_type: 'other', status: 'uploaded', file_name: `eye-blink-${number}.json`, mime_type: 'application/json', metadata }).select('*').single()
        if (inserted.error) throw inserted.error
        return NextResponse.json({ plan: { id: inserted.data.id, ...metadata } })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 400 })
    }
}
