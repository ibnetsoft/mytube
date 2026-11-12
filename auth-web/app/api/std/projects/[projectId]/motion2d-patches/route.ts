import {createHash, randomUUID} from 'crypto'
import {NextResponse} from 'next/server'
import sharp from 'sharp'
import {supabaseAdmin as db} from '@/lib/supabaseAdmin'
import {requireStdUser} from '@/lib/stdWeb'
import {coordinateSource} from '@/lib/stdSpeakerGeometry'
import {downloadGcsObject, uploadGcsBuffer} from '@/lib/gcsStorage'

export const dynamic = 'force-dynamic'
const roles = new Set(['mouth_closed', 'mouth_half', 'mouth_open', 'blink', 'hair'])
const digest = (b: Buffer) => createHash('sha256').update(b).digest('hex')

async function context(req: Request, projectId: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return {response: auth.response}
    const project = await db.from('std_projects').select('id,status,submitted_at').eq('id', projectId).eq('employee_email', auth.requester.email).maybeSingle()
    if (project.error) throw project.error
    if (!project.data || project.data.status === 'canceled') return {response: NextResponse.json({error:'프로젝트를 찾을 수 없습니다.'}, {status:404})}
    return {project: project.data}
}

export async function GET(req: Request, {params}: {params:{projectId:string}}) {
    try {
        const ctx = await context(req, params.projectId); if (ctx.response) return ctx.response
        const query = new URL(req.url).searchParams, scene = Number(query.get('scene')), imageId = query.get('imageId'), imageSha = query.get('imageSha256'), id = query.get('id')
        if (!Number.isInteger(scene) || scene < 1 || !imageId || !/^[a-f0-9]{64}$/.test(imageSha || '')) throw Error('씬과 원본 이미지를 확인해 주세요.')
        const result = await db.from('std_project_assets').select('id,metadata,created_at').eq('project_id',params.projectId).eq('scene_number',scene).eq('metadata->>kind','motion2d_patch').eq('metadata->>imageId',imageId).eq('metadata->>imageSha256',imageSha).in('status',['uploaded','assigned']).order('created_at',{ascending:false}).limit(100)
        if (result.error) throw result.error
        const assets = result.data || []
        if (id) {
            const asset = assets.find(a => a.id === id)
            if (!asset) return NextResponse.json({error:'패치를 찾을 수 없습니다.'},{status:404})
            const m = asset.metadata, bytes = await downloadGcsObject({bucket:m.gcs_bucket,objectPath:m.gcs_path})
            if (digest(bytes) !== m.sha256) throw Error('저장된 패치가 변경되었습니다.')
            return new NextResponse(new Uint8Array(bytes),{headers:{'Content-Type':'image/png','Cache-Control':'private, no-store'}})
        }
        return NextResponse.json({patches:assets.map(a=>({id:a.id,role:a.metadata.role,sha256:a.metadata.sha256,created_at:a.created_at}))},{headers:{'Cache-Control':'private, no-store'}})
    } catch (e:any) { return NextResponse.json({error:e.message},{status:400}) }
}

export async function POST(req: Request, {params}: {params:{projectId:string}}) {
    try {
        const ctx = await context(req, params.projectId); if (ctx.response) return ctx.response
        if (ctx.project?.submitted_at || ['approved','review_requested'].includes(ctx.project?.status || '')) throw Error('제출 전 프로젝트에서 편집해 주세요.')
        const form = await req.formData(), scene = Number(form.get('scene')), imageId = String(form.get('imageId') || ''), imageSha = String(form.get('imageSha256') || ''), role = String(form.get('role') || ''), file = form.get('file')
        if (!Number.isInteger(scene) || scene < 1 || !roles.has(role) || !/^[a-f0-9]{64}$/.test(imageSha) || !(file instanceof File) || file.size < 1 || file.size > 4*1024*1024) throw Error('씬, 패치 종류와 4MB 이하 PNG를 확인해 주세요.')
        const source = await db.from('std_project_assets').select('*').eq('project_id',params.projectId).eq('scene_number',scene).eq('asset_type','image').in('status',['uploaded','assigned']).order('created_at',{ascending:false}).limit(1).maybeSingle()
        if (source.error) throw source.error
        if (!source.data || source.data.id !== imageId) throw Error('씬 원본 이미지가 변경되었습니다. 다시 불러와 주세요.')
        const location = coordinateSource(source.data), original = await downloadGcsObject({bucket:location.bucket,objectPath:location.path})
        if (digest(original) !== imageSha) throw Error('원본 이미지가 변경되었습니다. 다시 불러와 주세요.')
        const raw = Buffer.from(await file.arrayBuffer()), meta = await sharp(raw,{limitInputPixels:40000000}).metadata(), dimensions = await sharp(original,{limitInputPixels:40000000}).metadata()
        if (meta.format !== 'png' || !meta.hasAlpha || !meta.width || !meta.height || !dimensions.width || !dimensions.height || meta.width !== dimensions.width || meta.height !== dimensions.height) throw Error('원본과 같은 크기의 투명 PNG가 필요합니다.')
        const stats = await sharp(raw).stats(), alpha = stats.channels[3]
        if (!alpha || alpha.min === 255 || alpha.max === 0) throw Error('패치에는 불투명한 부위와 투명한 배경이 모두 필요합니다.')
        const png = await sharp(raw).png().toBuffer(), sha = digest(png)
        const stored = await uploadGcsBuffer({objectPath:`std-motion2d/${params.projectId}/patches/${randomUUID()}.png`,data:png,contentType:'image/png'})
        const metadata = {kind:'motion2d_patch',version:1,role,imageId,imageSha256:imageSha,sha256:sha,width:meta.width,height:meta.height,gcs_bucket:stored.bucket,gcs_path:stored.path}
        const saved = await db.from('std_project_assets').insert({project_id:params.projectId,scene_number:scene,asset_type:'other',status:'uploaded',file_name:`motion2d-${role}.png`,mime_type:'image/png',metadata}).select('id,created_at').single()
        if (saved.error) throw saved.error
        return NextResponse.json({patch:{id:saved.data.id,role,sha256:sha,created_at:saved.data.created_at}})
    } catch (e:any) { return NextResponse.json({error:e.message},{status:400}) }
}
