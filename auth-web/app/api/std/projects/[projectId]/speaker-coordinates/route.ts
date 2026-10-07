import { NextResponse } from 'next/server'
import { createHash, randomUUID } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { readSceneImage } from '@/lib/stdSceneImageDownload'
import { downloadGcsObject } from '@/lib/gcsStorage'
import {
    coordinateCast,
    coordinateScenes,
    coordinateSource,
    savedSpeakerGeometry,
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
    const a = await db
        .from('std_project_assets')
        .select('*')
        .eq('project_id', projectId)
        .in('status', ['uploaded', 'assigned'])
        .order('created_at', { ascending: false })
    if (a.error) throw a.error
    return { project: p.data, assets: a.data || [], email: auth.requester.email }
}
function overview(project: any, assets: any[]) {
    const cast = coordinateCast(project),
        scenes = coordinateScenes(project, assets)
    const jobs = assets.filter((a) => a.metadata?.kind === 'ae_speaker_coordinates')
    const items = scenes.map((scene) => {
        const result = savedSpeakerGeometry(assets, cast, scene)
        const job = jobs.find(
            (a) =>
                a.metadata.input?.cast_key === JSON.stringify(cast) &&
                a.metadata.input?.scenes?.some(
                    (s: any) => s.number === scene.number && s.image?.id === scene.image?.id,
                ),
        )
        const meta = job?.metadata || {}
        const failure = meta.failures?.find((f: any) => f.number === scene.number)
        return {
            ...scene,
            result,
            error: result ? null : failure?.error || (Number(meta.current_scene) === scene.number ? meta.error : null),
            analysisState: meta.state,
            currentScene: meta.current_scene,
            heartbeatAt: meta.heartbeat_at || job?.updated_at,
        }
    })
    const results = items.flatMap((s) => (s.result ? [s.result] : []))
    return {
        count: items.length,
        completed: results.length,
        failed: items.filter((s) => !s.result && s.error).length,
        pending: items.filter((s) => !s.result && !s.error).length,
        confirmed: items.filter((s) => s.result?.origin === 'user').length,
        scenes: items,
        state: results.length === items.length ? 'ready' : 'needs_review',
        results,
        error: '웹에서 화자 위치를 직접 확정할 수 있습니다. 새로고침 후 위치 지정 버튼을 눌러 주세요.',
    }
}
export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const number = Number(new URL(req.url).searchParams.get('sceneNumber'))
        const scene = coordinateScenes(ctx.project, ctx.assets).find((s) => s.number === number)
        if (!scene?.image) return NextResponse.json({ error: '원본 이미지가 없습니다.' }, { status: 404 })
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
        return NextResponse.json(overview(project, assets))
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
        const speakers = validateSpeakerGeometry(body.speakers, names)
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
                    kind: 'speaker_coordinate_confirmation',
                    state: 'ready',
                    scene_key: scene.key,
                    confirmed_by: email,
                    confirmed_at: new Date().toISOString(),
                    results: [result],
                },
            })
            .select('*')
            .single()
        if (saved.error) throw saved.error
        return NextResponse.json(overview(fresh.project, [saved.data, ...fresh.assets]))
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 400 })
    }
}
