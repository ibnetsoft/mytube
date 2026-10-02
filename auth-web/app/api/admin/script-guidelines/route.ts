import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { isAuthResponse, requireAdmin, requireSuperAdmin } from '../_auth'
export const dynamic = 'force-dynamic'
export async function GET(req: Request) {
    const auth=await requireAdmin(req);if(isAuthResponse(auth))return auth
    const [versions,outcomes]=await Promise.all([
        supabaseAdmin.from('script_guideline_versions').select('*').order('version',{ascending:false}).limit(100),
        supabaseAdmin.from('script_guideline_outcomes').select('*').order('updated_at',{ascending:false}).limit(50)])
    if(versions.error || outcomes.error)return NextResponse.json({error:'지침 조회 실패'},{status:503})
    return NextResponse.json({items:versions.data || [],outcomes:outcomes.data || []})
}
export async function POST(req: Request) {
    const auth=await requireSuperAdmin(req);if(isAuthResponse(auth))return auth
    const body=await req.json().catch(()=>null)
    if(!body || typeof body!=='object')return NextResponse.json({error:'잘못된 요청'},{status:400})
    const text=(key:string)=>typeof body[key]==='string'?body[key].trim():''
    if(body.action==='propose'){
        const row=Object.fromEntries(['title','issue','instruction','category','language'].map(k=>[k,text(k)]))
        if(!row.title || row.title.length>200 || !row.issue || row.issue.length>4000 || !row.instruction || row.instruction.length>4000 || row.category.length>80 || !['','ko','ja','en','es','vi','th'].includes(row.language))return NextResponse.json({error:'제목·문제·지침과 적용 범위를 확인하세요.'},{status:400})
        const source=text('source_job_id')
        if(source && !/^[a-f0-9]{32}$/.test(source))return NextResponse.json({error:'관련 작업 ID 오류'},{status:400})
        const result=await supabaseAdmin.from('script_guideline_versions').insert({...row,...(source?{source_job_id:source}:{}),status:'pending'}).select('*').single()
        if(result.error)return NextResponse.json({error:'저장 실패. 관련 작업 ID를 확인하세요.'},{status:400})
        return NextResponse.json(result.data)
    }
    const transitions:Record<string,[string,string]>={approve:['pending','approved'],reject:['pending','rejected'],retire:['approved','retired']}
    const transition=transitions[text('action')],id=text('id'),note=text('note')
    if(!transition || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id) || note.length>1000 || (body.action!=='approve' && !note))return NextResponse.json({error:'검토 동작과 사유를 확인하세요.'},{status:400})
    const result=await supabaseAdmin.from('script_guideline_versions').update({status:transition[1],review_note:note,reviewed_at:new Date().toISOString()}).eq('id',id).eq('status',transition[0]).select('*').maybeSingle()
    if(result.error)return NextResponse.json({error:'검토 저장 실패'},{status:503})
    if(!result.data)return NextResponse.json({error:'지침 상태가 변경됐습니다. 새로고침하세요.'},{status:409})
    return NextResponse.json(result.data)
}
