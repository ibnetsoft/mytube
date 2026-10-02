import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { isAuthResponse, requireAdmin } from '../_auth'
export const dynamic = 'force-dynamic'
export async function GET(req: Request) {
 const auth=await requireAdmin(req);if(isAuthResponse(auth))return auth
 const [recent,active]=await Promise.all([
  supabaseAdmin.from('script_worker_jobs').select('id,title,mode,status,created_at,updated_at,job_record').order('created_at',{ascending:false}).limit(50),
  supabaseAdmin.from('script_worker_jobs').select('id,title,mode,status,created_at,updated_at,job_record').in('status',['queued','running'])])
 if(recent.error || active.error)return NextResponse.json({error:'대본워커 조회 실패'},{status:503})
 const jobs=Array.from(new Map([...(active.data || []),...(recent.data || [])].map(row=>[row.id,row])).values())
 return NextResponse.json({source:'script_worker_jobs',jobs,active_count:(active.data || []).length,generated_at:new Date().toISOString()})
}
export async function POST(req: Request) {
 const auth=await requireAdmin(req);if(isAuthResponse(auth))return auth
 return NextResponse.json({error:'이전 Hermes 대본 실행은 종료되었습니다. 이 컴퓨터의 대본워커에서 실행하세요.'},{status:410})
}
