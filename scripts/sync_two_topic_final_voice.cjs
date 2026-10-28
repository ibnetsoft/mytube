const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
require('node:events').defaultMaxListeners=64;
process.env.FFMPEG_PATH=path.resolve('venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe');
const rt=require('./std_web_runtime.cjs'),db=rt.load('supabaseAdmin').supabaseAdmin;
const IDS={3376:'05e173f1-46a4-42e6-b543-6d7ba4458368',3377:'dcf670cc-ace7-4c3f-861f-186441724d08'};
const V={Saori:'ozfS3gQtjFX3kQyJ12dX',Yukari:'80H5qqdq3bIO8OjFE6ue',Mio:'EVmK7c3z026INySFvQLP',JUN:'JOcmGzB8OFjY8MhjHHEf',Bill:'pqHfZKP75CvOlQylNhV4',George:'JBFqnCBsd6RMkjVDRZzb',Sarah:'EXAVITQu4vr4xnSDxMaL'};
const CAST={3376:{'お澄':V.Yukari,'おきぬ':V.Mio,'久兵衛':V.Bill,'清吉':V.JUN,'源助':V.George},3377:{'お紬':V.Mio,'佐平':V.JUN,'源蔵':V.Bill,'おきよ':V.Yukari,'お常':V.Sarah,'庄屋':V.George,'店の買い手':V.George,'集金先の店主':V.George,'織り手の老女':V.Sarah}};
const topic=Number(process.argv[2]);assert(IDS[topic]);const id=IDS[topic];
const folder=path.resolve('output/codex-local-console/two-topic-mouths',String(topic),'final-voice');fs.mkdirSync(folder,{recursive:true});
const write=(name,x)=>{const f=path.join(folder,name);fs.writeFileSync(f+'.tmp',JSON.stringify(x,null,2));fs.renameSync(f+'.tmp',f)};
const progress=x=>{write('progress.json',{...x,updated_at:new Date().toISOString()});console.log(JSON.stringify({topic,...x}))};
async function project(){const r=await db.from('std_projects').select('*').eq('id',id).single();if(r.error)throw r.error;return r.data}
async function main(){
 let p=await project();const q=p.project_payload;const backup=path.join(folder,'before-voice-assignment.json');if(!fs.existsSync(backup))write('before-voice-assignment.json',p);
 rt.load('stdProjectAssets').loadStdProjectAssets=async(database,projectId)=>{
  assert.equal(projectId,id);
  const [a,t]=await Promise.all([database.from('std_project_assets').select('*').eq('project_id',id).in('status',['uploaded','assigned']).or('asset_type.in.(audio,image,video),metadata->>kind.eq.ae_mouth_job').limit(1000),database.from('topics_queue').select('pregenerated_structure').eq('id',topic).single()]);if(a.error||t.error)return {data:null,error:a.error||t.error};
  const source=typeof t.data.pregenerated_structure==='string'?JSON.parse(t.data.pregenerated_structure):t.data.pregenerated_structure;
  return {data:[...a.data,...rt.load('stdGeneratedSpeakerGeometry').generatedSpeakerAssets(p,source,a.data)],error:null};
 };
 const narrator=topic===3377?'google_kr':V.Saori;
 const split=rt.load('stdDialogueAnnotations').splitSubtitleDialogueBlocks(q.subtitles,q.structure.dialogue_annotations,true,20);
 const originals=new Map(q.subtitles.map(s=>[s.id,s]));
 const rows=split.map(s=>{
  const parent=originals.get(String(s.id).replace(/-ai-\d+$/,''));if(parent?.text===s.text)s={...s,id:parent.id};
  const speaker=s.dialogue_kind==='dialogue'&&s.dialogue_speaker?s.dialogue_speaker:null;
  if(speaker&&!CAST[topic][speaker])throw Error('No approved voice assignment for '+speaker);
  return {...s,dialogue_kind:speaker?'dialogue':'narration',dialogue_speaker:speaker,voice_id:speaker?CAST[topic][speaker]:narrator,
   audio_regeneration_required:true,voice_assignment_pending:false};
 });
 const compact=rs=>rs.map(s=>s.text).join('').replace(/\s/g,'');assert.equal(compact(rows),compact(q.subtitles),'Subtitle text changed while classifying');
 const plan={topic,narrator,voice_map:CAST[topic],row_count:rows.length,dialogue_rows:rows.filter(s=>s.dialogue_kind==='dialogue').length,
  voices:rows.reduce((r,s)=>(r[s.voice_id]=(r[s.voice_id]||0)+1,r),{}),rows};write('voice-plan.json',plan);
 progress({phase:'plan',row_count:plan.row_count,dialogue_rows:plan.dialogue_rows,voices:plan.voices});
 if(process.argv.includes('--plan'))return;
 if(!q.final_voice_recovery?.assigned){
  await rt.load('stdContentIdentity').persistContentRevision(db,p);
  const updated={...q,subtitles:rows,subtitle_editor_snapshot:rows,voice_id:narrator,voice_map:CAST[topic],tts_model_id:'eleven_multilingual_v2',
    final_voice_recovery:{assigned:true,topic,source:'user_authorized_recommended_cast',assigned_at:new Date().toISOString()}};
  const r=await db.from('std_projects').update({project_payload:updated,updated_at:new Date().toISOString()}).eq('id',id).eq('updated_at',p.updated_at).select('*').single();if(r.error)throw r.error;p=r.data;
 } else {
  assert.deepEqual(p.project_payload.subtitles.map(s=>[s.text,s.voice_id]),rows.map(s=>[s.text,s.voice_id]),'Saved final voice plan changed');
 }
 const token=rt.load('desktopSession').signDesktopSessionToken(p.employee_email);
 // Use the actual web synthesis function locally with one verified owner session.
 // Avoid refetching the multi-megabyte source structure for every four-line batch.
 const {createRequire}=require('node:module'),req=createRequire(path.join(rt.web,'package.json')),ts=req('typescript');
 const routeFile=path.join(rt.web,'app/api/std/projects/[projectId]/tts/generate/route.ts');
 const content=rt.load('stdContentIdentity'),originalRevision=content.persistContentRevision,revisionCache=new Map();
 content.persistContentRevision=async(database,record)=>{
  const key=record.id+':'+content.projectContentIdentity(record).script_sha256;
  if(!revisionCache.has(key))revisionCache.set(key,originalRevision(database,record));
  return revisionCache.get(key);
 };
 const route={};new Function('exports','require',ts.transpileModule(fs.readFileSync(routeFile,'utf8')+'\nexport {runTts as runLocalTts};',{compilerOptions:{module:1,target:9,esModuleInterop:true}}).outputText)(route,name=>name.startsWith('@/lib/')?rt.load(name.slice(6)):req(name));
 const auth=await rt.load('stdWeb').requireStdUser(new Request('http://localhost/api/std/voices',{headers:{Authorization:'Bearer '+token}}));if(!auth.ok)throw Error('Project owner session validation failed');
 const body={provider:topic===3377?'google_free':'elevenlabs',voice_id:narrator,model_id:'eleven_multilingual_v2',speed:Number(q.tts_speed)||1,stability:.7,style:.45,
   text:rows.map(s=>s.text).join('\n'),voice_map:CAST[topic],voice_segments:rows.map(s=>({text:s.text,voice_id:s.voice_id,direction:s.voice_direction||''}))};
 async function send(payload){const r=await route.runLocalTts(payload,auth,p);const x=await r.json();if(!r.ok||!x.success)throw Error(`${x.stage||'tts'}: ${x.error||r.status}`);return x}
 const {data:assets,error}=await db.from('std_project_assets').select('id,metadata').eq('project_id',id).eq('metadata->>kind','vrew_segment_tts').in('status',['uploaded','assigned']).limit(1000);if(error)throw error;
 const keys=rt.load('stdSegmentAudioCache').segmentAudioKey;
 const missing=body.voice_segments.map((s,i)=>{const k=keys({text:s.text,provider:s.voice_id.startsWith('google_')?'google_free':'elevenlabs',voiceId:s.voice_id,modelId:body.model_id,speed:body.speed,direction:s.direction,stability:.7,style:.45,language:p.language||'ja'});return assets.some(a=>a.metadata?.kind==='vrew_segment_tts'&&a.metadata.cache_key===k)?null:i}).filter(i=>i!==null);
 progress({phase:'prepare',total:rows.length,exact_cached:rows.length-missing.length,missing:missing.length});
 if(process.argv.includes('--dialogue-only')){
  const selected=missing.filter(i=>rows[i].dialogue_kind==='dialogue');
  for(let j=0;j<selected.length;j++){const i=selected[j];await send({...body,mode:'prepare_narration_segments',text:body.voice_segments[i].text,voice_segments:[body.voice_segments[i]],segment_offset:i});progress({phase:'prepare_dialogue',prepared:j+1,total:selected.length})}
  progress({phase:'dialogue_completed',prepared:selected.length});return;
 }
 const needed=new Set(missing);let prepared=0;
 for(let offset=0;offset<rows.length;offset+=4){
  const batch=body.voice_segments.slice(offset,offset+4),count=batch.filter((_,i)=>needed.has(offset+i)).length;if(!count)continue;
  await send({...body,mode:'prepare_narration_segments',text:batch.map(s=>s.text).join('\n'),voice_segments:batch,segment_offset:offset});
  prepared+=count;progress({phase:'prepare',prepared,missing:missing.length,total:rows.length});
 }
 progress({phase:'assemble',total:rows.length});const result=await send({...body,mode:'assemble_narration_segments'});write('assembled-result.json',result);
 const current=await project();assert.deepEqual(current.project_payload.publish_metadata,q.publish_metadata);assert.deepEqual(current.project_payload.thumbnail_bg_url,q.thumbnail_bg_url);
 const {data:all,error:e}=await rt.load('stdProjectAssets').loadStdProjectAssets(db,id,'*');if(e)throw e;
 const {data:scenes,error:se}=await db.from('std_project_scenes').select('*').eq('project_id',id).order('scene_number');if(se)throw se;
 const job=await rt.load('stdSubmissionPipeline').ensureSyncedMouthPreview(current,scenes,all);
 progress({phase:'voice_completed',audio_asset_id:result.asset?.id,duration:result.asset?.metadata?.duration_seconds,mouth_job_id:job?.id,total:rows.length});
}
main().catch(e=>{progress({phase:'failed',error:e.message});process.exitCode=1});
