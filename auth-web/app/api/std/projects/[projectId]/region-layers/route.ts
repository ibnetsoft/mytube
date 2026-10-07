import { NextResponse } from 'next/server'
import { createHash, randomUUID } from 'crypto'
import sharp from 'sharp'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { coordinateSource } from '@/lib/stdSpeakerGeometry'
import { downloadGcsObject, uploadGcsBuffer } from '@/lib/gcsStorage'
import { regionLayerGeometry, regionLayerKey } from '@/lib/stdRegionMotion'
export const dynamic = 'force-dynamic'
export const maxDuration = 300
const digest = (b: Buffer | string) =>
    createHash('sha256').update(b).digest('hex')
async function context(req: Request, projectId: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const p = await db
        .from('std_projects')
        .select('id,status')
        .eq('id', projectId)
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
        .eq('project_id', projectId)
        .in('status', ['uploaded', 'assigned'])
        .order('created_at', { ascending: false })
    if (a.error) throw a.error
    return { assets: a.data || [] }
}
async function insert(projectId: string, scene: number, metadata: any) {
    const r = await db
        .from('std_project_assets')
        .insert({
            project_id: projectId,
            scene_number: scene,
            asset_type: 'other',
            status: 'uploaded',
            file_name: `${metadata.kind}.json`,
            mime_type: 'application/json',
            metadata,
        })
        .select('*')
        .single()
    if (r.error) throw r.error
    return { id: r.data.id, ...r.data.metadata }
}
export async function GET(
    req: Request,
    { params }: { params: { projectId: string } },
) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        const query = new URL(req.url).searchParams,
            id = query.get('id'),
            role = query.get('role')
        if (id && role) {
            const pack = ctx.assets!.find(
                (a) =>
                    a.id === id && a.metadata?.kind === 'region_layer_package',
            )
            const file = pack?.metadata?.result?.files?.find(
                (f: any) => f.role === role,
            )
            if (!file) throw new Error('레이어 파일이 없습니다.')
            const bytes = await downloadGcsObject({
                bucket: file.gcs_bucket,
                objectPath: file.gcs_path,
            })
            return new NextResponse(new Uint8Array(bytes), {
                headers: {
                    'Content-Type': 'image/png',
                    'Cache-Control': 'private, no-store',
                },
            })
        }
        return NextResponse.json(
            {
                packages: ctx
                    .assets!.filter(
                        (a) => a.metadata?.kind === 'region_layer_package',
                    )
                    .map((a) => ({ id: a.id, ...a.metadata })),
            },
            { headers: { 'Cache-Control': 'private, no-store' } },
        )
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
        const multipart = req.headers
            .get('content-type')
            ?.includes('multipart/form-data')
        const form = multipart ? await req.formData() : null
        const body: any = form ? Object.fromEntries(form) : await req.json()
        const number = Number(body.sceneNumber)
        const image = ctx.assets!.find(
            (a) =>
                a.asset_type === 'image' && Number(a.scene_number) === number,
        )
        if (!image || image.id !== body.imageId)
            throw new Error('원본 이미지가 변경됐습니다. 다시 불러와 주세요.')
        const source = coordinateSource(image),
            bytes = await downloadGcsObject({
                bucket: source.bucket,
                objectPath: source.path,
            }),
            sha = digest(bytes)
        if (sha !== body.imageSha256)
            throw new Error('원본 이미지가 변경됐습니다.')
        if (body.action === 'upload' && form) {
            const file = form.get('file')
            if (
                !(file instanceof File) ||
                file.size > 4 * 1024 * 1024 ||
                !file.size
            )
                throw new Error('4MB 이하의 PNG/JPEG 이미지를 선택해 주세요.')
            if (!['foreground', 'background'].includes(body.role))
                throw new Error('올바른 레이어 종류를 선택해 주세요.')
            const raw = Buffer.from(await file.arrayBuffer()),
                m = await sharp(raw, { limitInputPixels: 40000000 }).metadata(),
                original = await sharp(bytes).metadata()
            const ratio = Math.min(
                    1,
                    1920 / Math.max(original.width!, original.height!),
                ),
                w = Math.max(2, Math.floor((original.width! * ratio) / 2) * 2),
                h = Math.max(2, Math.floor((original.height! * ratio) / 2) * 2)
            if (
                !['png', 'jpeg', 'webp'].includes(m.format || '') ||
                !(
                    (m.width === w && m.height === h) ||
                    (m.width === original.width && m.height === original.height)
                )
            )
                throw new Error(
                    `원본 전체 캔버스(${original.width}×${original.height}) 또는 ${w}×${h}에 위치를 맞춰 올려 주세요.`,
                )
            const normalized = await sharp(raw).resize(w, h).png().toBuffer()
            if (body.role === 'foreground') {
                const stats = await sharp(normalized).stats()
                if (
                    !m.hasAlpha ||
                    stats.channels.at(-1)!.min === 255 ||
                    stats.channels.at(-1)!.max === 0
                )
                    throw new Error(
                        '부위 외곽은 투명하고 부위는 보이는 PNG를 올려 주세요.',
                    )
            }
            const stored = await uploadGcsBuffer({
                objectPath: `std-region-layers/${params.projectId}/uploads/${randomUUID()}.png`,
                data: normalized,
                contentType: 'image/png',
            })
            const asset = await insert(params.projectId, number, {
                kind: 'region_layer_upload',
                role: body.role,
                imageId: image.id,
                imageSha256: sha,
                gcs_bucket: stored.bucket,
                gcs_path: stored.path,
                sha256: digest(normalized),
                width: w,
                height: h,
            })
            return NextResponse.json({ asset })
        }
        if (body.action === 'approve') {
            const pack = ctx.assets!.find(
                (a) =>
                    a.id === body.packageId &&
                    a.metadata?.kind === 'region_layer_package',
            )
            if (
                !pack ||
                !['prepared', 'approved'].includes(pack.metadata.state) ||
                pack.metadata.input.image.id !== image.id ||
                pack.metadata.input.imageSha256 !== sha
            )
                throw new Error(
                    '현재 원본의 준비된 레이어를 먼저 확인해 주세요.',
                )
            if (body.reviewed !== true)
                throw new Error('외곽선·복원 배경·합성 결과를 확인해 주세요.')
            const r = await db
                .from('std_project_assets')
                .update({
                    metadata: {
                        ...pack.metadata,
                        state: 'approved',
                        reviewedAt: new Date().toISOString(),
                    },
                })
                .eq('id', pack.id)
                .eq('updated_at', pack.updated_at)
                .select('id')
            if (r.error) throw r.error
            if (!r.data?.length)
                throw new Error(
                    '레이어 상태가 변경됐습니다. 다시 확인해 주세요.',
                )
            return NextResponse.json({ approved: true })
        }
        if (body.action !== 'prepare')
            throw new Error('지원하지 않는 작업입니다.')
        const geometry = regionLayerGeometry(body.regions),
            backgroundAssetId = String(body.backgroundAssetId || '')
        const supplement = (id: string, role: string) => {
            const a = ctx.assets!.find(
                (a) =>
                    a.id === id &&
                    a.metadata?.kind === 'region_layer_upload' &&
                    Number(a.scene_number) === number &&
                    a.metadata.imageId === image.id &&
                    a.metadata.imageSha256 === sha &&
                    a.metadata.role === role,
            )
            if (!a)
                throw new Error(
                    '현재 이미지에 맞는 보완 이미지를 다시 올려 주세요.',
                )
            return { id: a.id, metadata: a.metadata }
        }
        const replacements = geometry
            .filter((g) => g.replacementAssetId)
            .map((g) => ({
                regionId: g.id,
                ...supplement(g.replacementAssetId, 'foreground'),
            }))
        if (geometry.some((g) => g.occluded && !g.replacementAssetId))
            throw new Error(
                '가려지거나 잘린 부위는 완성된 투명 PNG를 추가하거나 원본 이미지를 수정해 주세요.',
            )
        const key = regionLayerKey(
            image.id,
            sha,
            body.regions,
            backgroundAssetId,
        )
        const old = ctx.assets!.find(
            (a) =>
                a.metadata?.kind === 'region_layer_package' &&
                a.metadata.key === key &&
                ['queued', 'processing', 'prepared', 'approved'].includes(
                    a.metadata.state,
                ),
        )
        if (old)
            return NextResponse.json({
                package: { id: old.id, ...old.metadata },
            })
        const fresh = await context(req, params.projectId)
        if (fresh.response) return fresh.response
        if (
            fresh.assets!.find(
                (a) =>
                    a.asset_type === 'image' &&
                    Number(a.scene_number) === number,
            )?.id !== image.id
        )
            throw new Error('원본이 변경됐습니다.')
        const pack = await insert(params.projectId, number, {
            kind: 'region_layer_package',
            state: 'queued',
            key,
            editorRegions: body.regions,
            input: {
                number,
                image: { id: image.id, metadata: image.metadata },
                imageSha256: sha,
                geometry,
                replacements,
                background: backgroundAssetId
                    ? supplement(backgroundAssetId, 'background')
                    : null,
            },
        })
        return NextResponse.json({ package: pack })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 400 })
    }
}
