import { loadSpeakerCoordinateAssets } from '@/lib/stdSpeakerCoordinateAssets'
import { speakerCoordinateOverview } from '@/lib/stdSpeakerCoordinateOverview'
import { NextResponse } from 'next/server'
import { createHash, randomUUID } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { readSceneImage } from '@/lib/stdSceneImageDownload'
import { prepareSpeakerVideoFrame } from '@/lib/stdSpeakerVideoFrame'
import { downloadGcsObject } from '@/lib/gcsStorage'
import {
    coordinateCast,
    coordinateScenes,
    coordinateSource,
    validateSpeakerGeometry,
} from '@/lib/stdSpeakerGeometry'
export const dynamic = 'force-dynamic'
export const maxDuration = 300

async function context(req: Request, projectId: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const p = await db
        .from('std_projects')
        .select('*')
        .eq('id', projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()
    if (p.error) throw p.error
    if (!p.data || p.data.status === 'canceled')
        return { response: NextResponse.json({ error: 'Project not available' }, { status: 404 }) }
    const assets = await loadSpeakerCoordinateAssets(db, [projectId])
    return { project: p.data, assets, email: auth.requester.email }
}
export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const number = Number(new URL(req.url).searchParams.get('sceneNumber'))
        const scene = coordinateScenes(ctx.project, ctx.assets).find((s) => s.number === number)
        if (!scene?.image) return NextResponse.json({ error: '원본 이미지가 없습니다.' }, { status: 404 })
        const expectedKey = new URL(req.url).searchParams.get('sceneKey')
        if (expectedKey && expectedKey !== scene.key)
            return NextResponse.json({ error: '이미지나 화자가 변경됐습니다. 다시 확인해 주세요.' }, { status: 409 })
        const source = coordinateSource(scene.image)
        const image = await readSceneImage(req, {
            metadata: {
                cowork_image_asset: { storage_provider: 'gcs', gcs_bucket: source.bucket, gcs_path: source.path },
            },
        })
        return new NextResponse(new Uint8Array(image.buffer), {
            headers: { 'Content-Type': image.contentType, 'Cache-Control': 'private, no-store' },
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 400 })
    }
}
export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const { project, assets } = ctx,
            body = await req.json().catch(() => ({}))
        if (body.action === 'prepare_video') {
            const scene = coordinateScenes(project, assets).find(s => s.number === Number(body.sceneNumber))
            if (!scene?.video || body.videoId !== scene.video.id)
                return NextResponse.json({ error: '원본 영상이 변경됐습니다. 다시 불러와 주세요.' }, { status: 409 })
            await prepareSpeakerVideoFrame(db, params.projectId, scene, assets)
            const latest = await context(req, params.projectId)
            if (latest.response) return latest.response
            return NextResponse.json(speakerCoordinateOverview(latest.project, latest.assets))
        }
        // Opening the editor only reads status. AI work is explicitly requested per scene.
        if (body.action === 'analyze') {
            const scene = coordinateScenes(project, assets).find((s) => s.number === Number(body.sceneNumber))
            if (!scene?.image || scene.rows.some((r) => !r.speaker))
                return NextResponse.json({ error: '원본 이미지와 저장된 화자를 먼저 확인해 주세요.' }, { status: 400 })
            const existing = assets.find(
                (a) =>
                    a.metadata?.kind === 'ae_speaker_coordinates' &&
                    a.metadata.scene_key === scene.key &&
                    ['queued', 'processing'].includes(a.metadata.state),
            )
            if (!existing) {
                const cast = coordinateCast(project),
                    input = { cast, cast_key: JSON.stringify(cast), scenes: [scene] }
                const result = await db
                    .from('std_project_assets')
                    .insert({
                        project_id: params.projectId,
                        asset_type: 'other',
                        status: 'uploaded',
                        file_name: 'speaker-coordinates.json',
                        mime_type: 'application/json',
                        metadata: {
                            kind: 'ae_speaker_coordinates',
                            state: 'queued',
                            fingerprint: createHash('sha256')
                                .update(scene.key + randomUUID())
                                .digest('hex'),
                            scene_key: scene.key,
                            input,
                            results: [],
                            failures: [],
                        },
                    })
                    .select('*')
                    .single()
                if (result.error) throw result.error
                assets.unshift(result.data)
            }
        }
        return NextResponse.json(speakerCoordinateOverview(project, assets))
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 400 })
    }
}
export async function PATCH(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const { project, assets, email } = ctx,
            body = await req.json()
        const scene = coordinateScenes(project, assets).find((s) => s.number === Number(body.sceneNumber))
        if (!scene?.image || body.sceneKey !== scene.key)
            return NextResponse.json(
                { error: '이미지나 화자가 변경됐습니다. 새로고침 후 다시 확인해 주세요.' },
                { status: 409 },
            )
        const names = [...new Set<string>(scene.rows.map((r) => r.speaker))]
        const isDraft = body.draft === true
        const submitted = isDraft && Array.isArray(body.speakers)
            ? body.speakers.filter((s: any) => s.status === 'offscreen' || (s.face_box && s.mouth_box)) : body.speakers
        if (isDraft && (!Array.isArray(submitted) || submitted.some((s: any) => !names.includes(s.speaker))
            || new Set(submitted.map((s: any) => s.speaker)).size !== submitted.length))
            throw new Error('저장할 화자 정보를 확인해 주세요.')
        const selectedNames = isDraft ? names.filter(name => submitted.some((s: any) => s.speaker === name)) : names
        const speakers = validateSpeakerGeometry(submitted, selectedNames)
        const source = coordinateSource(scene.image)
        if (!source.path) throw new Error('원본 이미지 저장 위치가 없습니다.')
        const original = await downloadGcsObject({ bucket: source.bucket, objectPath: source.path })
        const imageHash = createHash('sha256').update(original).digest('hex')
        if (body.imageSha256 !== imageHash)
            return NextResponse.json(
                { error: '원본 이미지가 변경됐습니다. 이미지를 다시 불러온 뒤 지정해 주세요.' },
                { status: 409 },
            )
        // Recheck after I/O; never attach a confirmation to a changed source/speaker list.
        const fresh = await context(req, params.projectId)
        if (fresh.response) return fresh.response
        const current = coordinateScenes(fresh.project, fresh.assets).find((s) => s.number === scene.number)
        if (current?.key !== scene.key)
            return NextResponse.json({ error: '이미지나 화자가 변경됐습니다. 다시 확인해 주세요.' }, { status: 409 })
        const result = {
            number: scene.number,
            image_id: scene.image.id,
            source_path: source.path,
            source_sha256: imageHash,
            speakers,
        }
        const saved = await db
            .from('std_project_assets')
            .insert({
                project_id: params.projectId,
                scene_number: scene.number,
                asset_type: 'other',
                status: 'uploaded',
                file_name: `speaker-confirmation-${scene.number}.json`,
                mime_type: 'application/json',
                metadata: {
                    kind: isDraft ? 'speaker_coordinate_draft' : 'speaker_coordinate_confirmation',
                    state: isDraft ? 'draft' : 'ready',
                    scene_key: scene.key,
                    confirmed_by: email,
                    confirmed_at: new Date().toISOString(),
                    results: [result],
                },
            })
            .select('*')
            .single()
        if (saved.error) throw saved.error
        return NextResponse.json(speakerCoordinateOverview(fresh.project, [saved.data, ...fresh.assets]))
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 400 })
    }
}
