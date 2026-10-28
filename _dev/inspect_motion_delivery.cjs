const {load,root}=require('../scripts/std_web_runtime.cjs'),fs=require('node:fs'),path=require('node:path')
async function main(){
 const db=load('supabaseAdmin').supabaseAdmin
 const psds=await db.from('std_project_assets').select('id,project_id,scene_number,file_name,status,created_at').ilike('file_name','%.psd').order('created_at',{ascending:false}).limit(200);if(psds.error)throw psds.error
 const ids=[...new Set((psds.data||[]).map(x=>x.project_id))]
 console.log('PSD project assets',JSON.stringify(psds.data))
 if(!ids.length)return
 const projects=await db.from('std_projects').select('*').in('id',ids);if(projects.error)throw projects.error
 const receipts=[]
 for(const p of projects.data){const a=await load('stdProjectAssets').loadStdProjectAssets(db,p.id,'*');if(a.error)throw a.error;const s=await db.from('std_project_scenes').select('*').eq('project_id',p.id).order('scene_number');if(s.error)throw s.error
  let audio=null,error='';try{load('stdLipSync').lipSyncPlan(p,s.data,a.data);audio=load('stdContentIdentity').selectNarrationAsset(p,a.data)}catch(e){error=e.message}
  const info={id:p.id,title:p.title,status:p.status,updated_at:p.updated_at,method:load('stdMotionStudio').motionProductionMethod(p),scenes:s.data.length,psds:psds.data.filter(x=>x.project_id===p.id).length,final_audio:audio?{id:audio.id,name:audio.file_name,timeline:audio.metadata?.subtitle_timeline?.length,end:audio.metadata?.subtitle_timeline?.at(-1)?.end}:null,audio_error:error,audio_candidates:a.data.filter(x=>x.asset_type==='audio'&&x.scene_number==null).map(x=>({id:x.id,name:x.file_name,status:x.status,kind:x.metadata?.kind,duration:x.metadata?.duration_seconds,finalized:x.metadata?.finalized}))}
  receipts.push(info)
 }
 fs.mkdirSync(path.join(root,'output/motion-final-production'),{recursive:true});fs.writeFileSync(path.join(root,'output/motion-final-production/candidates.json'),JSON.stringify(receipts,null,2));console.log(JSON.stringify(receipts,null,2))
}
main().catch(e=>{console.error(e.message);process.exitCode=1})
