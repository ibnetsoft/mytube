const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {load}=require('./std_web_runtime.cjs');
const db=load('supabaseAdmin').supabaseAdmin,gcs=load('gcsStorage'),identity=load('stdContentIdentity');
const id='e9233112-f0d7-4b35-91bf-2f892844eb30',oldId='b841bdd1-ea89-49db-bc85-c81c604be103';
const dir=path.resolve('output/project-recovery-e9233112'),receipt=path.join(dir,'subtitle-only-render-receipt.json');
(async()=>{
 if(fs.existsSync(receipt)){console.log(JSON.stringify({queue_id:JSON.parse(fs.readFileSync(receipt)).id,reused_receipt:true}));return;}
 // The user explicitly ended the expanded AE review flow. Cancel only its job.
 const j=await db.from('std_project_assets').select('metadata').eq('id','9824529b-32f6-4513-a39e-678d496522fc').single();if(j.error)throw j.error;
 const {worker_token,...jm}=j.data.metadata;
 const stopped=await db.from('std_project_assets').update({metadata:{...jm,state:'obsolete',automatic:false,auto_pending:false,obsolete_reason:'User requested subtitle restoration and rendering only; retain previously rendered visuals.'},updated_at:new Date().toISOString()}).eq('id','9824529b-32f6-4513-a39e-678d496522fc');if(stopped.error)throw stopped.error;
 const [p,a,o,last]=await Promise.all([
  db.from('std_projects').select('*').eq('id',id).single(),
  db.from('std_project_assets').select('*').eq('id','563c1bc2-d9f2-4c43-92d8-1b76b457031e').single(),
  db.from('remote_render_queue').select('*').eq('id',oldId).single(),
  db.from('remote_render_queue').select('metadata').eq('metadata->>std_web_project_id',id).order('created_at',{ascending:false}).limit(1),
 ]);for(const r of [p,a,o,last])if(r.error)throw r.error;
 const project=p.data,audio=a.data,rows=project.project_payload.subtitles;
 assert.equal(rows.length,714);for(const n of [37,38])assert.equal(rows.filter(r=>r.scene_number===n).length,7);
 const narration=identity.assertNarrationIdentity(project,audio,rows),content=identity.projectContentIdentity(project);
 const config=JSON.parse(fs.readFileSync('_dev/artifacts/latest_render_exact_config.json','utf8'));
 assert.equal(config.std_web_project_id,id);assert.equal(config.images.length,77);
 const originalVisualFiles=JSON.stringify(config.asset_manifest.files.filter(f=>['image','video'].includes(f.asset_type)));
 config.subtitles=rows.map(r=>({text:r.text,start:Number(r.start_num??r.start_time??r.start),end:Number(r.end_num??r.end_time??r.end),volume:r.volume??100,scene_number:r.scene_number,dialogue_kind:r.dialogue_kind,dialogue_speaker:r.editor_speaker?.name||r.dialogue_speaker||null,voice_id:r.voice_id,voice_name:r.voice_name}));
 config.audio_duration=audio.metadata.duration_seconds;config.worker_tts=false;
 config.image_timing_starts=config.scene_numbers.map((n,i)=>{
  const row=config.subtitles.find(r=>r.scene_number>=n);
  return row?row.start:Math.min(config.audio_duration-.04,config.subtitles.at(-1).start);
 });
 config.image_timing_starts[0]=0;
 assert(config.image_timing_starts.every((t,i)=>i===0||t>config.image_timing_starts[i-1]),'Scene starts must remain ordered');
 config.content_identity=content;config.subtitle_content_identity={...content,...narration,row_count:714};
 const af=config.asset_manifest.files.find(f=>f.asset_type==='audio');assert(af);
 Object.assign(af,{gcs_bucket:audio.metadata.gcs_bucket,gcs_path:audio.metadata.gcs_path,storage_bucket:audio.metadata.gcs_bucket,storage_path:audio.metadata.gcs_path,size:audio.file_size,content_identity:{...content,...narration,asset_id:audio.id,source_sha256:audio.metadata.sha256}});
 delete af.gcs_signed_url;
 assert.equal(JSON.stringify(config.asset_manifest.files.filter(f=>['image','video'].includes(f.asset_type))),originalVisualFiles);
 const version=Number(last.data[0]?.metadata?.render_version||8)+1,task=crypto.randomUUID();
 config.render_version=version;
 // Existing packaging is retained byte-for-byte, including title and thumbnail.
 config.subtitle_recovery={source_render_queue_id:oldId,restored_count:714,visuals_unchanged:true,ae_review_requested:false};
 const storagePath=`std-projects/${id}/render-packages/${task}/config.json`,bytes=Buffer.from(JSON.stringify(config));
 await gcs.uploadGcsBuffer({objectPath:storagePath,data:bytes,contentType:'application/json'});
 const url=await gcs.createGcsSignedReadUrl({objectPath:storagePath,expiresInMinutes:240});
 const metadata={...o.data.metadata,package_transport:'gcs_config',job_stage:'pending',render_version:version,previous_render_queue_id:oldId,content_identity:content,audio_asset_id:audio.id,topic_queue_id:3373,admin_publish_ready:false,admin_publish_status:'render_pending',asset_file_id:task,config_file_id:task,asset_web_link:url,config_web_link:url,gcs_config:{bucket:gcs.gcsBucketName(),path:storagePath,signed_url:url},subtitle_recovery:config.subtitle_recovery};
 for(const k of ['gcs_path','gcs_public_url','gcs_thumbnail_url','result_public_url','result_metadata_file_id','completed_at','audio_provenance','ae_mouth_job_id'])delete metadata[k];
 const queued=await db.from('remote_render_queue').insert({id:task,project_id:o.data.project_id,project_name:o.data.project_name,email:o.data.email,status:'pending',progress:0,message:'복원된 자막 적용: 기존 영상·연출 유지, 렌더링만 진행',render_mode:'gcs_api',asset_file_id:task,asset_file_name:'config.json',metadata,updated_at:new Date().toISOString()}).select('*').single();if(queued.error)throw queued.error;
 fs.writeFileSync(receipt,JSON.stringify(queued.data,null,2));fs.writeFileSync(path.join(dir,'subtitle-only-render-config.json'),JSON.stringify(config));
 const saved=await db.from('std_projects').update({progress_payload:{...project.progress_payload,remote_task_id:task,remote_render_queue_id:task,remote_render_mode:'gcs_api',latest_render_version:version,admin_publish_status:'render_pending'},updated_at:new Date().toISOString()}).eq('id',id);if(saved.error)throw saved.error;
 console.log(JSON.stringify({queue_id:task,topic:3373,subtitles:714,existing_clips:77,render_version:version,ae_review:false,upload:false}));
})().catch(e=>{console.error(e.message);process.exitCode=1});
