const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const rt=require('./std_web_runtime.cjs'),db=rt.load('supabaseAdmin').supabaseAdmin;
const jobs={3376:'0db3979f-cded-4f78-899d-687123bffb87',3377:'9159c849-ebbf-4d5a-8429-d25b397cca50'};
async function main(){for(const [topic,id] of Object.entries(jobs)){
 if(process.argv[2]&&process.argv[2]!==topic)continue;
 const folder=path.join(rt.root,'output/codex-local-console/two-topic-mouths',topic,'final-voice');
 const before=JSON.parse(fs.readFileSync(path.join(folder,'before-voice-assignment.json'),'utf8'));
 const {data:job,error:je}=await db.from('std_project_assets').select('project_id,metadata').eq('id',id).single();if(je)throw je;
 const {data:p,error:pe}=await db.from('std_projects').select('id,title,status,project_payload').eq('id',job.project_id).single();if(pe)throw pe;
 const q=p.project_payload;
 assert.equal(p.title,before.title);assert.deepEqual(q.publish_metadata,before.project_payload.publish_metadata);assert.deepEqual(q.thumbnail_bg_url,before.project_payload.thumbnail_bg_url);
 assert.equal(p.status,'in_progress');assert.equal(q.subtitle_source_audio_id,job.metadata.input.audio.id);
 assert.deepEqual(q.subtitle_editor_snapshot,q.subtitles);assert.notEqual(q.audio_regeneration_required,true);
 const {data:assets,error:ae}=await db.from('std_project_assets').select('id,scene_number,asset_type,status,metadata').eq('project_id',p.id).eq('asset_type','video').in('status',['uploaded','assigned']).order('created_at',{ascending:false}).order('id',{ascending:false});if(ae)throw ae;
 const delivered=job.metadata.input.mouth_work_scene_numbers.map(n=>{const a=assets.find(a=>a.scene_number===n);assert(a);assert.equal(a.metadata.ae_mouth_fingerprint,job.metadata.fingerprint);assert.equal(a.metadata.source_audio_id,q.subtitle_source_audio_id);assert.equal(a.metadata.voice_synced,true);assert.equal(a.metadata.timing_mode,'final_voice');assert(a.metadata.gcs_path);return n});
 assert.equal(delivered.length,10);assert.equal(job.metadata.actual_voice_verified.clips,10);
 const remote=await Promise.allSettled(delivered.map(async n=>{const a=assets.find(a=>a.scene_number===n),m=a.metadata;const object=await rt.load('gcsStorage').getGcsObjectMetadata({bucket:m.gcs_bucket,objectPath:m.gcs_path});assert(object.size>0);assert.equal(object.contentType,'video/mp4');}));for(const result of remote)if(result.status==='rejected')throw result.reason;
 const assembled=JSON.parse(fs.readFileSync(path.join(folder,'assembled-result.json'),'utf8')).asset;
 assert.equal(assembled.id,q.subtitle_source_audio_id);assert.deepEqual(q.subtitles.map(s=>[s.text,s.voice_id,s.start,s.end]),assembled.metadata.subtitle_timeline.map(s=>[s.text,s.voice_id,s.start,s.end]));
 const receipt={topic:Number(topic),actual_voice_scenes:delivered,audio_id:q.subtitle_source_audio_id,subtitle_rows:q.subtitles.length,title_thumbnail_metadata_preserved:true,latest_web_video_assets_verified:true,status:p.status};
 fs.writeFileSync(path.join(folder,'delivery-verification.json'),JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));
}}
main().catch(e=>{console.error(e.message);process.exitCode=1});
