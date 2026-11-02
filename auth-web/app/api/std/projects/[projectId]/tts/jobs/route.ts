import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { publicTtsJob, ttsJobFingerprint, ttsSourceHash } from '@/lib/stdTtsJobs'
import { subtitleSpeakerProgress } from '@/lib/stdSubtitleSpeakerProgress'
export const dynamic = 'force-dynamic'
async function owner(req: Request, projectId: string, includeSpeech = false) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const columns = includeSpeech
        ? 'id,employee_email,script:project_payload->>script,subtitles:project_payload->subtitles,voice_id:project_payload->>voice_id,tts_speed:project_payload->tts_speed'
        : 'id,employee_email'
    const { data, error } = await supabaseAdmin.from('std_projects').select(columns).eq('id', projectId).eq('employee_email', auth.requester.email).maybeSingle()
    if (error) throw error
    if (!data) return { response: NextResponse.json({ error: 'Project not found' }, { status: 404 }) }
    const row: any = data
    const project = includeSpeech ? { ...row, project_payload: {
        script: row.script, subtitles: row.subtitles, voice_id: row.voice_id, tts_speed: row.tts_speed,
    } } : row
    return { project, requester: auth.requester }
}
export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await owner(req, params.projectId)
    if (auth.response) return auth.response
    const { data, error } = await supabaseAdmin.from('std_tts_jobs').select('id,project_id,status,ready,total,reused,generated,error,updated_at').eq('project_id', params.projectId).order('created_at', { ascending: false }).limit(1).maybeSingle()
    if (error) throw error
    return NextResponse.json({ success: true, job: publicTtsJob(data) })
}
export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await owner(req, params.projectId, true)
    if (auth.response) return auth.response
    const body = await req.json()
    delete body.mode
    delete body.segment_preview
    delete body.cache_only
    const segments = body.voice_segments
    if (!Array.isArray(segments) || !segments.length || segments.length > 5000 || segments.some((s: any) => !String(s.text || '').trim() || !s.voice_id)) {
        return NextResponse.json({ error: '자막과 성우를 모두 지정해 주세요.' }, { status: 400 })
    }
    const fingerprint = ttsJobFingerprint(body)
    const saved = (auth.project!.project_payload?.subtitles || []).filter((s: any) => String(s.text || '').trim())
    const speakers = saved.map((s: any) => s.editor_speaker || (s.dialogue_speaker ? { name: s.dialogue_speaker } : null))
    const progress = subtitleSpeakerProgress(saved, new Map(), speakers)
    if (progress.confirmed !== progress.total || saved.length !== segments.length || saved.some((s: any, i: number) =>
        String(s.text).trim() !== String(segments[i].text).trim() || String(s.voice_id || body.voice_id) !== String(segments[i].voice_id))) {
        return NextResponse.json({ error: '저장된 자막·성우와 요청이 일치하지 않습니다. 자막을 저장하고 화자를 모두 지정해 주세요.' }, { status: 409 })
    }
    const active = await supabaseAdmin.from('std_tts_jobs').select('*').eq('project_id', params.projectId).in('status', ['queued','processing']).maybeSingle()
    if (active.error) throw active.error
    if (active.data) {
        if (active.data.fingerprint !== fingerprint) return NextResponse.json({ error: '다른 설정의 TTS 작업이 진행 중입니다. 완료 후 다시 요청해 주세요.' }, { status: 409 })
        return NextResponse.json({ success: true, job: publicTtsJob(active.data) })
    }
    const { data, error } = await supabaseAdmin.from('std_tts_jobs').insert({ project_id: params.projectId,
        owner_email: auth.requester!.email, user_id: auth.requester!.user.id, fingerprint, request: body,
        source_hash: ttsSourceHash(auth.project), script: String(auth.project!.project_payload?.script || ''), total: segments.length }).select('*').single()
    if (error?.code === '23505') return GET(req, { params })
    if (error) throw error
    return NextResponse.json({ success: true, job: publicTtsJob(data) }, { status: 202 })
}
