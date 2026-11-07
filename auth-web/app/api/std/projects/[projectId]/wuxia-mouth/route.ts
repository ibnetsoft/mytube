import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
export const dynamic='force-dynamic'
/** Read-only: generation belongs to the local script worker. Never expose leases/input. */
export async function GET(req:Request,{params}:{params:{projectId:string}}) {
 const auth=await requireStdUser(req)
 if(!auth.ok)return auth.response
 const {data:p,error}=await supabaseAdmin.from('std_projects').select('id,employee_email,project_payload').eq('id',params.projectId).maybeSingle()
 const email=String(auth.requester.email||'').toLowerCase()
 if(error||!p||(!email.startsWith('admin')&&!email.startsWith('worker')&&email!==String(p.employee_email||'').toLowerCase()))return NextResponse.json({success:false},{status:404})
 const structure=p.project_payload?.structure||{},pkg=structure.wuxia_ae_package
 if(structure.wuxia_mouth_policy?.auto_prepare!==true)return NextResponse.json({success:true,states:[]})
 return NextResponse.json({success:true,project_id:p.id,policy:structure.wuxia_mouth_policy,
  audio_id:p.project_payload?.subtitle_source_audio_id,report:pkg?.mouth_timing||pkg?.mouth_preparation,
  states:(pkg?.scenes||[]).flatMap((sc:any)=>(sc.states||[]).map((st:any)=>({scene_id:sc.scene_id,graphics:sc.graphics,asset_id:st.asset_id,sha256:st.sha256,ambient_loops:st.ambient_loops||[],energy_preparation:st.energy_preparation,energy_only_motion:st.energy_only_motion===true,dialogue_mouths:st.dialogue_mouths||[]})))},
  {headers:{'Cache-Control':'private, no-store'}})
}
