const fs=require('fs'),path=require('path'),crypto=require('crypto');
const runtime=require('../scripts/std_web_runtime.cjs');
const db=runtime.load('supabaseAdmin').supabaseAdmin;
const dir=path.join(runtime.root,'_dev/artifacts/elevenlabs-v4-new-live');fs.mkdirSync(dir,{recursive:true});
const oldId='05e173f1-46a4-42e6-b543-6d7ba4458368';
const voice='FGY2WhTYpPnrIDTdsKH5';
const texts=['비가 그친 아침, 작은 창문으로 햇살이 들어왔습니다.','오늘은 새로운 이야기가 시작되는 날입니다.'];
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
async function snapshot(id){
 const p=await db.from('std_projects').select('*').eq('id',id).single();if(p.error)throw p.error;
 const assets=[];for(let offset=0;;offset+=1000){const q=await db.from('std_project_assets').select('*').eq('project_id',id).order('id').range(offset,offset+999);if(q.error)throw q.error;assets.push(...q.data.filter(a=>a.asset_type==='audio'||a.metadata?.kind==='vrew_segment_tts'));if(q.data.length<1000)break;}
 return {project:p.data,assets,projectHash:hash(p.data),assetsHash:hash(assets)};
}
async function setup(){
 const receipt=path.join(dir,'receipt.json');if(fs.existsSync(receipt)){console.log(fs.readFileSync(receipt,'utf8'));return;}
 const old=await snapshot(oldId);fs.writeFileSync(path.join(dir,'existing-before.json'),JSON.stringify(old,null,2));
 const id=crypto.randomUUID(),now=new Date().toISOString();
 const subtitles=texts.map((text,i)=>({id:crypto.randomUUID(),text,voice_id:voice,scene_number:1,dialogue_override:false,dialogue_kind:'narration',start_time:String(i*4),end_time:String((i+1)*4),start_num:i*4,end_num:(i+1)*4,translation_manual:true}));
 const payload={title:'Eleven v4 새 음성·자막 검증 (2026-10-19)',script:texts.join('\n'),subtitles,voice_id:voice,tts_speed:1,ae_mouth:{enabled:false},verification_only:true};
 const p=await db.from('std_projects').insert({id,employee_email:old.project.employee_email,category_id:old.project.category_id,title:payload.title,status:'in_progress',language:'ko',user_id:old.project.user_id,assigned_duration_minutes:1,estimated_payout:0,updated_at:now,project_payload:payload,progress_payload:{verification_only:true}}).select('id,title').single();if(p.error)throw p.error;
 fs.writeFileSync(receipt,JSON.stringify({projectId:id,title:p.data.title,voiceId:voice,texts,createdAt:now,url:`https://studio.airing.work/std?tab=subtitle_vrew&projectId=${id}`},null,2));
 const s=await db.from('std_project_scenes').insert({project_id:id,scene_number:1,scene_text:texts.join('\n'),duration_seconds:8,start_seconds:0,end_seconds:8});if(s.error)throw s.error;
 console.log(fs.readFileSync(receipt,'utf8'));
}
async function inspect(){const receipt=JSON.parse(fs.readFileSync(path.join(dir,'receipt.json')));const sample=await snapshot(receipt.projectId);fs.writeFileSync(path.join(dir,'sample-after.json'),JSON.stringify(sample,null,2));const before=JSON.parse(fs.readFileSync(path.join(dir,'existing-before.json')));const after=await snapshot(oldId);const summary={newProject:receipt.projectId,audioAssets:sample.assets.map(a=>({id:a.id,type:a.asset_type,createdAt:a.created_at,model:a.metadata?.model_id,models:a.metadata?.elevenlabs_model_ids,timeline:a.metadata?.subtitle_timeline,sha256:a.metadata?.sha256})),existingProjectUnchanged:before.projectHash===after.projectHash,existingRecordingsUnchanged:before.assetsHash===after.assetsHash};fs.writeFileSync(path.join(dir,'verification.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));}
(process.argv[2]==='inspect'?inspect():setup()).catch(e=>{console.error(e.message);process.exitCode=1});
