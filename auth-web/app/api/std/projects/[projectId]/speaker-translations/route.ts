import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { charactersFromPayload } from '@/lib/stdCharacterProtection'

export const dynamic = 'force-dynamic'
export const maxDuration = 30

const JOB_TABLE = 'std_subtitle_translation_jobs'
const KIND = 'speaker_names'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const text = (value: unknown) => typeof value === 'string' ? value.trim() : ''

function speakerContext(name: string, payload: any, sourcePayload: any) {
    const character = [...charactersFromPayload(payload), ...charactersFromPayload(sourcePayload)]
        .find(item => text(item?.name) === name) || {}
    const annotationScenes = payload?.structure?.dialogue_annotations?.scenes
    const excerpts: string[] = []
    for (const scene of Array.isArray(annotationScenes) ? annotationScenes : []) {
        if (scene?.spans?.some((span: any) => text(span?.speaker) === name)) {
            const excerpt = text(scene.source_text).slice(0, 600)
            if (excerpt && !excerpts.includes(excerpt)) excerpts.push(excerpt)
        }
        if (excerpts.length >= 3) break
    }
    const script = text(payload?.script || payload?.original_worker_script || sourcePayload?.pregenerated_script)
    const position = script.indexOf(name)
    if (position >= 0 && excerpts.length < 3) excerpts.push(script.slice(Math.max(0, position - 120), position + name.length + 240))
    return {
        reading: text(character.name_reading || character.reading || character.furigana || character.name_kana || character.romanized_name).slice(0, 100),
        role: text(character.role).slice(0, 160),
        gender: text(character.gender).slice(0, 30),
        excerpts,
    }
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    let body: any
    try { body = await req.json() } catch {
        return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 })
    }
    if (!['ko', 'th'].includes(body?.target_language) || !Array.isArray(body?.names)
        || body.names.length === 0 || body.names.length > 100
        || body.names.some((name: any) => typeof name !== 'string' || !name.trim() || name.trim().length > 80 || /[\u0000-\u001f\u007f]/.test(name))
        || (body.job_id !== undefined && (typeof body.job_id !== 'string' || !UUID.test(body.job_id)))) {
        return NextResponse.json({ success: false, error: 'Valid Korean or Thai speaker names are required' }, { status: 400 })
    }
    const names: string[] = body.names.map((name: string) => name.trim()).sort()
    if (new Set(names).size !== names.length) {
        return NextResponse.json({ success: false, error: 'Speaker names must be unique' }, { status: 400 })
    }
    const language: 'ko' | 'th' = body.target_language
    // requireStdUser resolves authorized administrator impersonation before ownership is checked.
    const { data: project, error } = await supabaseAdmin.from('std_projects')
        .select('id,employee_email,project_payload,source_payload')
        .eq('id', params.projectId).eq('employee_email', auth.requester.email).maybeSingle()
    if (error) return NextResponse.json({ success: false, error: 'Project query failed' }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const payload = project.project_payload || {}
    const cached = payload.speaker_name_translations?.[language] || {}
    const characters = [...charactersFromPayload(payload), ...charactersFromPayload(project.source_payload)]
    const translations: Record<string, string> = Object.create(null)
    names.forEach(name => {
        const character = characters.find(item => text(item?.name) === name)
        const localized = text(character?.[`name_${language}`]) || text(cached[name])
        if (localized) translations[name] = localized
    })
    const reply = (extra = {}, status = 200) => NextResponse.json({ success: true, translations, provider: 'local-codex', ...extra }, { status })
    const missing = names.flatMap((name, index) => translations[name] ? [] : [{
        index, source_text: name, context: speakerContext(name, payload, project.source_payload),
    }])
    if (!missing.length) return reply()

    const query = () => supabaseAdmin.from(JOB_TABLE)
        .select('id,status,result_blocks,source_blocks,error,translation_kind')
        .eq('project_id', project.id).eq('target_language', language).eq('translation_kind', KIND)
    let job: any
    if (body.job_id) {
        const found = await query().eq('id', body.job_id).maybeSingle()
        if (found.error) return NextResponse.json({ success: false, error: 'Speaker translation job query failed' }, { status: 500 })
        job = found.data
        if (!job || job.translation_kind !== KIND || !Array.isArray(job.source_blocks)
            || job.source_blocks.some((block: any) => !names.includes(block.source_text))) {
            return NextResponse.json({ success: false, error: 'Speaker translation request has changed' }, { status: 409 })
        }
    } else {
        const requestHash = createHash('sha256').update(JSON.stringify({ kind: KIND, version: 1, language, blocks: missing })).digest('hex')
        const found = await query().eq('request_hash', requestHash).maybeSingle()
        if (found.error) return NextResponse.json({ success: false, error: 'Speaker translation job query failed' }, { status: 500 })
        job = found.data
        if (!job) {
            const created = await supabaseAdmin.from(JOB_TABLE).upsert({
                project_id: project.id, target_language: language, translation_kind: KIND,
                request_hash: requestHash, source_blocks: missing, cached_blocks: [],
            }, { onConflict: 'project_id,target_language,request_hash', ignoreDuplicates: true })
            if (created.error) return NextResponse.json({ success: false, error: 'Speaker translation job could not be queued' }, { status: 500 })
            const fetched = await query().eq('request_hash', requestHash).single()
            if (fetched.error) return NextResponse.json({ success: false, error: 'Speaker translation job query failed' }, { status: 500 })
            job = fetched.data
        } else if (job.status === 'failed') {
            const retried = await supabaseAdmin.from(JOB_TABLE).update({
                status: 'queued', error: null, started_at: null, completed_at: null,
                created_at: new Date().toISOString(),
            }).eq('id', job.id).eq('translation_kind', KIND).eq('status', 'failed')
            if (retried.error) return NextResponse.json({ success: false, error: 'Speaker translation retry failed' }, { status: 500 })
            job.status = 'queued'
        }
    }
    if (!job) return NextResponse.json({ success: false, error: 'Speaker translation job not found' }, { status: 500 })
    if (job.status === 'failed') return NextResponse.json({ success: false, error: job.error || 'Local speaker translation failed' }, { status: 502 })
    if (job.status !== 'completed') return reply({ pending: true, job_id: job.id }, 202)
    for (const block of Array.isArray(job.result_blocks) ? job.result_blocks : []) {
        const source = job.source_blocks?.find((item: any) => item.index === block.index && item.source_text === block.source_text)
        if (source && names.includes(source.source_text) && text(block.translated_text) && !translations[source.source_text]) {
            translations[source.source_text] = text(block.translated_text)
        }
    }
    if (names.some(name => !translations[name])) {
        return NextResponse.json({ success: false, error: 'Some speaker names were not translated' }, { status: 502 })
    }
    return reply()
}
