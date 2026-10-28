const fs=require('fs'),path=require('path'),crypto=require('crypto');
const runtime=require('../scripts/std_web_runtime.cjs'),db=runtime.load('supabaseAdmin').supabaseAdmin;
const dir=path.join(runtime.root,'_dev/artifacts/v4-performance-ja');
const prior=['05e173f1-46a4-42e6-b543-6d7ba4458368','dca4a1fa-fc04-41eb-b1cf-3e05e1f08742','0fcac845-2fc7-46f0-b8b0-ae7bfd52875d'];
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
async function snapshot(id){const p=await db.from('std_projects').select('*').eq('id',id).single();if(p.error)throw p.error;const assets=[];for(let offset=0;;offset+=1000){const q=await db.from('std_project_assets').select('*').eq('project_id',id).order('id').range(offset,offset+999);if(q.error)throw q.error;assets.push(...q.data.filter(a=>a.asset_type==='audio'||a.metadata?.kind==='vrew_segment_tts'));if(q.data.length<1000)break;}return {project:p.data,assets,projectHash:hash(p.data),assetHash:hash(assets)}}
async function main(){
 const file=path.join(dir,'live-receipt.json');
 if(process.argv[2]==='inspect'){
  const receipt=JSON.parse(fs.readFileSync(file));const sample=await snapshot(receipt.projectId);fs.writeFileSync(path.join(dir,'live-snapshot.json'),JSON.stringify(sample,null,2));
  const before=JSON.parse(fs.readFileSync(path.join(dir,'protected-before.json')));const unchanged=[];for(const old of before){const after=await snapshot(old.project.id);unchanged.push({id:old.project.id,scriptAndProjectUnchanged:old.projectHash===after.projectHash,recordingsUnchanged:old.assetHash===after.assetHash,count:after.assets.length})}
  fs.writeFileSync(path.join(dir,'protected-verification.json'),JSON.stringify(unchanged,null,2));
  console.log(JSON.stringify({assets:sample.assets.map(a=>({id:a.id,type:a.asset_type,model:a.metadata?.model_id,performance:a.metadata?.voice_performance,timeline:a.metadata?.subtitle_timeline})),unchanged}));return;
 }
 if(fs.existsSync(file)){console.log(fs.readFileSync(file,'utf8'));return;}
 const protectedRows=[];for(const id of prior)protectedRows.push(await snapshot(id));fs.writeFileSync(path.join(dir,'protected-before.json'),JSON.stringify(protectedRows,null,2));
 const generated=JSON.parse(fs.readFileSync(path.join(dir,'new-script.json'))),id=crypto.randomUUID(),voice='FGY2WhTYpPnrIDTdsKH5',now=new Date().toISOString();
 const subtitles=generated.structure.scenes.map((scene,i)=>({id:crypto.randomUUID(),text:scene.scene_text,scene_number:i+1,voice_id:voice,dialogue_override:false,dialogue_kind:'narration',translation_manual:true,start_num:i*4,end_num:(i+1)*4,start_time:String(i*4),end_time:String((i+1)*4)}));
 const payload={...generated,subtitles,voice_id:voice,tts_speed:1,ae_mouth:{enabled:false},verification_only:true};
 const old=protectedRows[0].project;
 const p=await db.from('std_projects').insert({id,employee_email:old.employee_email,user_id:old.user_id,category_id:old.category_id,title:generated.title,status:'in_progress',language:generated.language,assigned_duration_minutes:1,estimated_payout:0,updated_at:now,project_payload:payload,progress_payload:{verification_only:true}});if(p.error)throw p.error;
 fs.writeFileSync(file,JSON.stringify({projectId:id,voiceId:voice,createdAt:now,texts:subtitles.map(s=>s.text),tags:generated.structure.audio_performance.scenes.map(s=>s.cues.map(c=>c.tag)),url:`https://studio.airing.work/std?tab=subtitle_vrew&projectId=${id}`},null,2));
 const s=await db.from('std_project_scenes').insert(generated.structure.scenes.map((scene,i)=>({project_id:id,scene_number:i+1,scene_title:`연기 비교 ${i+1}`,scene_text:scene.scene_text,metadata:{start_seconds:i*4,end_seconds:(i+1)*4,duration_seconds:4}})));if(s.error)throw s.error;
 console.log(fs.readFileSync(file,'utf8'));
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
