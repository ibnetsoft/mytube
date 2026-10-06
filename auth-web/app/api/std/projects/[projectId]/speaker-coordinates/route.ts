import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { dialogueSceneIndex } from '@/lib/stdDialogueSceneIndex'
export const dynamic = 'force-dynamic'
export async function POST(req: Request, {params}: {params:{projectId:string}}) {
    try {
        const auth = await requireStdUser(req); if (!auth.ok) return auth.response
        const p = await db.from('std_projects').select('*').eq('id',params.projectId).eq('employee_email',auth.requester.email).maybeSingle()
        if (p.error) throw p.error
        if (!p.data || p.data.status === 'canceled') return NextResponse.json({error:'Project not available'},{status:404})
        const a = await db.from('std_project_assets').select('*').eq('project_id',params.projectId).in('status',['uploaded','assigned']).order('created_at',{ascending:false})
        if (a.error) throw a.error
        const payload = p.data.project_payload || {}, structure = payload.structure || {}, subtitles = payload.subtitles || []
        const index = dialogueSceneIndex(subtitles)
        const cast = {main:structure.main_character || payload.main_character || {}, supporting:structure.supporting_characters || payload.supporting_characters || [], scene_cast:structure.scene_cast || []}
        const scenes = index.scenes.filter(s => s.scene_number >= 19).map(s => {
            const image = a.data.find(x => x.asset_type === 'image' && Number(x.scene_number) === s.scene_number)
            if (!image) throw new Error(`${s.scene_number}번 씬의 원본 이미지가 필요합니다.`)
            if (!s.speakers.length || s.subtitle_indices.some(i => !subtitles[i].dialogue_speaker)) throw new Error(`${s.scene_number}번 씬의 화자를 먼저 확인해 주세요.`)
            const source = structure.scenes?.find((r:any) => Number(r.scene_number ?? r.scene_order) === s.scene_number)
            return {number:s.scene_number, image:{id:image.id,metadata:image.metadata}, text:source?.scene_text || subtitles.filter((r:any) => Number(r.scene_number)===s.scene_number).map((r:any)=>r.text).join(''),
                rows:s.subtitle_indices.map(i => ({kind:'dialogue',speaker:subtitles[i].dialogue_speaker,text:subtitles[i].text}))}
        })
        const input = {cast,cast_key:JSON.stringify(cast),scenes}
        const fingerprint = createHash('sha256').update(JSON.stringify(input)).digest('hex')
        const existing = a.data.find(x => x.metadata?.kind === 'ae_speaker_coordinates' && x.metadata.fingerprint === fingerprint)
        const body = await req.json().catch(() => ({}))
        if (existing && body.retry && existing.metadata.state === 'needs_review') {
            const retry = await db.from('std_project_assets').update({metadata:{...existing.metadata,state:'queued',error:null},updated_at:new Date().toISOString()}).eq('id',existing.id).eq('updated_at',existing.updated_at)
            if (retry.error) throw retry.error
            return NextResponse.json({state:'queued',count:scenes.length,results:existing.metadata.results || []})
        }
        if (existing) return NextResponse.json({state:existing.metadata.state,count:scenes.length,error:existing.metadata.error,results:existing.metadata.results || []})
        if (!scenes.length) return NextResponse.json({state:'ready',count:0,results:[]})
        const jobId = `${fingerprint.slice(0,8)}-${fingerprint.slice(8,12)}-4${fingerprint.slice(13,16)}-a${fingerprint.slice(17,20)}-${fingerprint.slice(20,32)}`
        const result = await db.from('std_project_assets').insert({id:jobId,project_id:params.projectId,asset_type:'other',status:'uploaded',file_name:'speaker-coordinates.json',mime_type:'application/json',
            metadata:{kind:'ae_speaker_coordinates',state:'queued',fingerprint,input,results:[]}}).select('id').single()
        if (result.error) throw result.error
        return NextResponse.json({state:'queued',count:scenes.length,results:[]})
    } catch(error:any) { return NextResponse.json({error:error.message},{status:400}) }
}
