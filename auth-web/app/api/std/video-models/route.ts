import { createHash } from 'crypto'
import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { protectYoutubeCredentials, readYoutubeCredentials } from '@/lib/stdYoutubeChannelOAuth'
import { validateVideoModel } from '@/lib/stdVideoModels'

export const dynamic = 'force-dynamic'
type Catalog = { models: Array<ReturnType<typeof validateVideoModel> & { secret: string }>; active_id: string | null }
function publicCatalog(catalog: Catalog) {
    return { models: catalog.models.map(({ secret, ...model }) => ({ ...model, has_key: Boolean(secret) })), active_id: catalog.active_id }
}
async function context(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    // Account-scoped encrypted storage; credentials never enter auth metadata or project snapshots.
    const key = 'std_video_models_' + createHash('sha256').update(auth.requester.email.trim().toLowerCase()).digest('hex')
    const encryptionKey = process.env.VIDEO_MODEL_ENCRYPTION_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY
    if (!encryptionKey) throw new Error('storage unavailable')
    const result = await supabaseAdmin.from('global_settings').select('value').eq('key', key).maybeSingle()
    if (result.error) throw result.error
    const catalog: Catalog = result.data?.value ? readYoutubeCredentials(result.data.value, encryptionKey) : { models: [], active_id: null }
    return { key, encryptionKey, catalog }
}
export async function GET(req: Request) {
    try {
        const ctx = await context(req)
        if (ctx.response) return ctx.response
        return NextResponse.json(publicCatalog(ctx.catalog!), { headers: { 'Cache-Control': 'no-store' } })
    } catch { return NextResponse.json({ error: '영상 모델 설정을 불러올 수 없습니다.' }, { status: 503 }) }
}
export async function POST(req: Request) {
    try {
        const ctx = await context(req)
        if (ctx.response) return ctx.response
        const body = await req.json()
        const catalog = ctx.catalog!
        try {
            if (body.action === 'save') {
                const model = validateVideoModel(body.model)
                const prior = catalog.models.find(item => item.id === model.id)
                const secret = String(body.api_key || '').trim() || prior?.secret || ''
                if (!secret || secret.length > 8192) throw new Error('API 키를 입력해 주세요.')
                if (!prior && catalog.models.length >= 20) throw new Error('최대 20개까지 등록할 수 있습니다.')
                catalog.models = [...catalog.models.filter(item => item.id !== model.id), { ...model, secret }]
            } else if (body.action === 'delete') {
                catalog.models = catalog.models.filter(item => item.id !== body.id)
                if (catalog.active_id === body.id) catalog.active_id = null
            } else if (body.action === 'apply') {
                if (!catalog.models.some(item => item.id === body.id)) throw new Error('등록된 모델을 선택해 주세요.')
                if (validateVideoModel(catalog.models.find(item=>item.id===body.id)).provider==='unconfigured') throw new Error('모델을 수정해 API 방식을 먼저 지정해 주세요.')
                catalog.active_id = body.id
            } else throw new Error('지원하지 않는 작업입니다.')
        } catch (error: any) { return NextResponse.json({ error: error.message }, { status: 400 }) }
        const result = await supabaseAdmin.from('global_settings').upsert({ key: ctx.key!, value: protectYoutubeCredentials(catalog, ctx.encryptionKey!), updated_at: new Date().toISOString() }, { onConflict: 'key' })
        if (result.error) throw result.error
        return NextResponse.json(publicCatalog(catalog), { headers: { 'Cache-Control': 'no-store' } })
    } catch { return NextResponse.json({ error: '영상 모델 설정을 저장할 수 없습니다. 잠시 후 다시 시도해 주세요.' }, { status: 503 }) }
}
