import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { coordinateSource } from '@/lib/stdSpeakerGeometry'
import { downloadGcsObject, createGcsSignedReadUrl } from '@/lib/gcsStorage'
import {
    motionSceneTimeline,
    validateRegionMotions,
} from '@/lib/stdRegionMotion'
export const dynamic = 'force-dynamic'
export const maxDuration = 300
async function context(req: Request, id: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const p = await db
        .from('std_projects')
        .select('*')
        .eq('id', id)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()
    if (p.error) throw p.error
    if (!p.data || p.data.status === 'canceled')
        return {
            response: NextResponse.json(
                { error: '프로젝트를 찾을 수 없습니다.' },
                { status: 404 },
            ),
        }
    const a = await db
        .from('std_project_assets')
        .select('*')
        .eq('project_id', id)
        .in('status', ['uploaded', 'assigned'])
        .order('created_at', { ascending: false })
    if (a.error) throw a.error
    return { project: p.data, assets: a.data || [] }
}
function scenes(ctx: any) {
    const numbers = [
        ...new Set<number>(
            ctx.assets
                .filter((a: any) => a.asset_type === 'image')
                .map((a: any) => Number(a.scene_number)),
        ),
    ]
        .filter((n) => n > 0)
        .sort((a, b) => a - b)
    return numbers.map((number) => {
        const image = ctx.assets.find(
            (a: any) =>
                a.asset_type === 'image' && Number(a.scene_number) === number,
        )
        const plan = ctx.assets.find(
            (a: any) =>
                a.metadata?.kind === 'region_motion_plan' &&
                Number(a.scene_number) === number,
        )
        return {
            number,
            imageId: image.id,
            ...motionSceneTimeline(
                ctx.project.project_payload?.subtitles || [],
                number,
            ),
            plan: plan
                ? { id: plan.id, updatedAt: plan.updated_at, ...plan.metadata }
                : null,
        }
    })
}
export async function GET(
    req: Request,
    { params }: { params: { projectId: string } },
) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const previewId = new URL(req.url).searchParams.get('preview')
        if (previewId) {
            const plan = ctx.assets!.find(
                (a: any) =>
                    a.id === previewId &&
                    a.metadata?.kind === 'region_motion_plan' &&
                    a.metadata.state === 'ready',
            )
            if (!plan?.metadata.result?.gcs_path)
                throw new Error('완료된 영상이 없습니다.')
            const result = plan.metadata.result
            return NextResponse.json(
                {
                    url: await createGcsSignedReadUrl({
                        bucket: result.gcs_bucket,
                        objectPath: result.gcs_path,
                        expiresInMinutes: 60,
                    }),
                },
                { headers: { 'Cache-Control': 'private, no-store' } },
            )
        }
        const imageNumber = new URL(req.url).searchParams.get('image')
        if (imageNumber) {
            const asset = ctx.assets!.find(
                (a: any) =>
                    a.asset_type === 'image' &&
                    Number(a.scene_number) === Number(imageNumber),
            )
            if (!asset) throw new Error('원본 이미지가 없습니다.')
            const source = coordinateSource(asset),
                bytes = await downloadGcsObject({
                    bucket: source.bucket,
                    objectPath: source.path,
                })
            return new NextResponse(new Uint8Array(bytes), {
                headers: {
                    'Content-Type': asset.mime_type || 'image/png',
                    'Cache-Control': 'private, no-store',
                },
            })
        }
        return NextResponse.json({ scenes: scenes(ctx) })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 400 })
    }
}
export async function POST(
    req: Request,
    { params }: { params: { projectId: string } },
) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const body = await req.json(),
            number = Number(body.sceneNumber),
            scene = scenes(ctx).find((s) => s.number === number)
        if (!scene) throw new Error('원본 이미지가 없습니다.')
        const image = ctx.assets!.find((a: any) => a.id === scene.imageId),
            source = coordinateSource(image)
        if (body.action === 'apply') {
            const plan = ctx.assets!.find(
                (a: any) =>
                    a.id === body.planId &&
                    a.id === scene.plan?.id &&
                    a.metadata?.kind === 'region_motion_plan',
            )
            if (!plan || plan.metadata.state !== 'ready')
                throw new Error('완료된 최신 AE 영상을 먼저 확인해 주세요.')
            const saved = plan.metadata.input
            if (
                saved.image.id !== image.id ||
                JSON.stringify(saved.timeline) !==
                    JSON.stringify(
                        motionSceneTimeline(
                            ctx.project.project_payload?.subtitles || [],
                            number,
                        ),
                    )
            )
                throw new Error(
                    '이미지나 자막 시간이 변경됐습니다. 다시 렌더링해 주세요.',
                )
            const bytes = await downloadGcsObject({
                bucket: source.bucket,
                objectPath: source.path,
            })
            if (
                createHash('sha256').update(bytes).digest('hex') !==
                saved.imageSha256
            )
                throw new Error('원본 이미지가 변경됐습니다.')
            const fresh = await context(req, params.projectId)
            if (fresh.response) return fresh.response
            const latest = scenes(fresh).find((s) => s.number === number)
            if (
                !latest ||
                latest.plan?.id !== plan.id ||
                latest.imageId !== saved.image.id ||
                JSON.stringify(
                    motionSceneTimeline(
                        fresh.project.project_payload?.subtitles || [],
                        number,
                    ),
                ) !== JSON.stringify(saved.timeline)
            )
                throw new Error(
                    '확인한 영상의 설정이나 원본이 변경됐습니다. 다시 확인해 주세요.',
                )
            const result = plan.metadata.result
            if (!result?.gcs_path || !result?.gcs_bucket)
                throw new Error('AE 결과 파일이 없습니다.')
            const existing = ctx.assets!.find(
                (a: any) =>
                    a.asset_type === 'video' &&
                    a.metadata?.region_motion_plan_id === plan.id,
            )
            if (!existing) {
                const added = await db.from('std_project_assets').insert({
                    project_id: params.projectId,
                    scene_number: number,
                    asset_type: 'video',
                    status: 'assigned',
                    file_name: `scene-${number}-region-motion.mp4`,
                    mime_type: 'video/mp4',
                    metadata: {
                        ...result,
                        storage_provider: 'gcs',
                        postprocess_mode: 'region_motion',
                        region_motion_plan_id: plan.id,
                        timing_locked: true,
                        reviewed_by_user: true,
                    },
                })
                if (added.error) throw added.error
            }
            return NextResponse.json({ applied: true })
        }
        if (!['save', 'render'].includes(body.action))
            throw new Error('지원하지 않는 작업입니다.')
        if (body.imageId !== image.id)
            throw new Error('원본 이미지가 변경됐습니다. 다시 불러와 주세요.')
        const timeline = motionSceneTimeline(
            ctx.project.project_payload?.subtitles || [],
            number,
        )
        const regions =
            body.action === 'save' &&
            Array.isArray(body.regions) &&
            !body.regions.length
                ? []
                : validateRegionMotions(body.regions, timeline)
        const bytes = await downloadGcsObject({
            bucket: source.bucket,
            objectPath: source.path,
        })
        const imageSha256 = createHash('sha256').update(bytes).digest('hex')
        if (body.imageSha256 !== imageSha256)
            throw new Error('원본 이미지가 변경됐습니다. 다시 불러와 주세요.')
        const fresh = await context(req, params.projectId)
        if (fresh.response) return fresh.response
        const current = scenes(fresh).find((s) => s.number === number)
        if (
            current?.imageId !== image.id ||
            JSON.stringify(current?.subtitles) !==
                JSON.stringify(timeline.subtitles)
        )
            throw new Error(
                '이미지나 자막 시간이 변경됐습니다. 다시 불러와 주세요.',
            )
        const input = {
            version: 1,
            number,
            image: { id: image.id, metadata: image.metadata },
            imageSha256,
            timeline,
            regions,
        }
        const fingerprint = createHash('sha256')
            .update(JSON.stringify(input))
            .digest('hex')
        if (
            scene.plan?.fingerprint === fingerprint &&
            ['queued', 'processing', 'ready'].includes(scene.plan.state)
        )
            return NextResponse.json({ plan: scene.plan })
        const added = await db
            .from('std_project_assets')
            .insert({
                project_id: params.projectId,
                scene_number: number,
                asset_type: 'other',
                status: 'uploaded',
                file_name: `region-motion-${number}.json`,
                mime_type: 'application/json',
                metadata: {
                    kind: 'region_motion_plan',
                    state: body.action === 'render' ? 'queued' : 'draft',
                    fingerprint,
                    input,
                },
            })
            .select('*')
            .single()
        if (added.error) throw added.error
        return NextResponse.json({
            plan: { id: added.data.id, ...added.data.metadata },
        })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 400 })
    }
}
