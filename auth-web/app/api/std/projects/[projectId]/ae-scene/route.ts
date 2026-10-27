import { NextResponse } from 'next/server'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { loadStdProjectAssets } from '@/lib/stdProjectAssets'
import { aeSceneHash, aeScenePreparationInput, aeSceneSelections, aeSceneSources, preparedAeScenes } from '@/lib/stdAeScenePreparation'

export const dynamic = 'force-dynamic'

async function context(req: Request, id: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const p = await db.from('std_projects').select('*').eq('id', id).eq('employee_email', auth.requester.email).maybeSingle()
    if (p.error) throw p.error
    if (!p.data) return { response: NextResponse.json({ error: '프로젝트를 찾을 수 없습니다.' }, { status: 404 }) }
    const [s, a] = await Promise.all([
        db.from('std_project_scenes').select('*').eq('project_id', id).order('scene_number'),
        loadStdProjectAssets(db, id, '*'),
    ])
    if (s.error) throw s.error
    if (a.error) throw a.error
    return { project: p.data, scenes: s.data || [], assets: a.data || [], userId: auth.requester.user.id }
}
const editable = (p: any) => !p.submitted_at && !['review_requested', 'approved', 'canceled'].includes(p.status)
const sceneAssets = (assets: any[], number: number) => assets.filter(a => a.metadata?.kind !== 'ae_scene_preparation' || Number(a.scene_number) === number)
function summary(ctx: any) {
    const sources = aeSceneSources(ctx.assets), selections = aeSceneSelections(ctx.assets)
    return { editable: editable(ctx.project), scenes: ctx.scenes.map((scene: any) => {
        const number = Number(scene.scene_number), source = sources.get(number), selection = selections.get(number)
        let issue = ''
        if (selection?.metadata.enabled !== false && selection?.metadata.state === 'prepared') {
            try { preparedAeScenes(ctx.project, ctx.scenes, sceneAssets(ctx.assets, number)) }
            catch (error: any) { issue = error.message }
        }
        const authored=(ctx.project.project_payload?.structure?.scenes||[]).find((s:any)=>Number(s.scene_number||s.scene_order)===number)
        return { depth_effects:(authored?.scene_direction_plan?.depth_effects||[]).map((e:any)=>e.type), number, title: scene.scene_title, source: source ? { id: source.id, file_name: source.file_name } : null,
            preparation: selection ? { id: selection.id, enabled: selection.metadata.enabled !== false, state: issue ? 'stale' : selection.metadata.state,
                direction_text: selection.metadata.input?.direction_text || '', requested_effects: selection.metadata.input?.requested_effects, error: issue || selection.metadata.error || '',
                progress: selection.metadata.progress || '', plan: selection.metadata.result?.plan || null } : null }
    }) }
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        return NextResponse.json(summary(ctx), { headers: { 'Cache-Control': 'private, no-store' } })
    } catch (error: any) { return NextResponse.json({ error: error.message }, { status: 400 }) }
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const ctx = await context(req, params.projectId)
        if (ctx.response) return ctx.response
        if (!editable(ctx.project)) return NextResponse.json({ error: '제출 전에 PSD 연출을 준비해 주세요.' }, { status: 409 })
        const body = await req.json(), number = Number(body.scene_number)
        if (!Number.isInteger(number) || !ctx.scenes!.some(s => Number(s.scene_number) === number)) throw new Error('씬 번호를 확인해 주세요.')
        if (!['prepare', 'disable'].includes(body.action)) throw new Error('지원하지 않는 작업입니다.')
        const current = aeSceneSelections(ctx.assets!).get(number)
        let input: any, fingerprint: string
        if (body.action === 'disable') {
            if (!current || current.metadata.enabled === false) return NextResponse.json(summary(ctx))
            input = current.metadata.input
            fingerprint = current.metadata.fingerprint
        } else {
            const direction = String(body.direction_text || '').trim()
            if (!direction || direction.length > 4000) throw new Error('원하는 연출을 1~4,000자로 입력해 주세요.')
            input = aeScenePreparationInput(ctx.project, ctx.scenes!, ctx.assets!, number, direction, body.requested_effects)
            if (body.source_asset_id !== input.source_psd?.id) throw new Error('PSD가 바뀌었습니다. 새로고침한 뒤 다시 준비해 주세요.')
            fingerprint = aeSceneHash(input)
            if (current?.metadata.enabled !== false && current?.metadata.fingerprint === fingerprint) {
                if (['queued', 'processing'].includes(current?.metadata.state)) return NextResponse.json(summary(ctx))
                if (current?.metadata.state === 'prepared') {
                    try {
                        if (preparedAeScenes(ctx.project, ctx.scenes!, sceneAssets(ctx.assets!, number)).get(number)?.id === current.id) return NextResponse.json(summary(ctx))
                    } catch { /* A corrupt or stale receipt can be repaired with a fresh request. */ }
                }
            }
        }
        // One deterministic UUID per transition makes retries atomic at the table PK.
        // There is no separate claim file that can strand a request after a crash.
        const key = aeSceneHash({ project: ctx.project.id, number, action: body.action, fingerprint, previous: current?.id || null })
        const jobId = `${key.slice(0, 8)}-${key.slice(8, 12)}-5${key.slice(13, 16)}-a${key.slice(17, 20)}-${key.slice(20, 32)}`
        // Detect submission/source changes before committing the immutable request.
        const fresh = await context(req, params.projectId)
        if (fresh.response) return fresh.response
        const recovered = fresh.assets!.find(a => a.id === jobId)
        if (recovered) return NextResponse.json(summary(fresh))
        if (!editable(fresh.project) || fresh.project.updated_at !== ctx.project.updated_at
            || aeSceneSelections(fresh.assets!).get(number)?.id !== current?.id) throw new Error('프로젝트 상태가 바뀌었습니다. 새로고침해 주세요.')
        if (body.action === 'prepare' && aeSceneHash(aeScenePreparationInput(fresh.project, fresh.scenes!, fresh.assets!, number, input.direction_text, input.requested_effects)) !== fingerprint)
            throw new Error('원본이나 대본이 바뀌었습니다. 새로고침한 뒤 다시 준비해 주세요.')
        const added = await db.from('std_project_assets').insert({ id: jobId, project_id: ctx.project.id, scene_number: number,
            asset_type: 'other', status: 'uploaded', mime_type: 'application/json', file_name: `ae-scene-${number}-${fingerprint}.json`,
            metadata: { kind: 'ae_scene_preparation', enabled: body.action === 'prepare', state: body.action === 'prepare' ? 'queued' : 'disabled',
                fingerprint, input, results: [], requested_by: ctx.userId },
        }).select('*').single()
        if (added.error) {
            if (added.error.code !== '23505') throw added.error
            const retry = await context(req, params.projectId)
            if (retry.response) return retry.response
            if (!retry.assets!.some(a => a.id === jobId)) throw added.error
            return NextResponse.json(summary(retry))
        }
        return NextResponse.json(summary({ ...ctx, assets: [added.data, ...ctx.assets!] }), { status: body.action === 'prepare' ? 202 : 200 })
    } catch (error: any) { return NextResponse.json({ error: error.message }, { status: 400 }) }
}
