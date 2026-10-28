const fs = require('node:fs');
const runtime = require('../scripts/std_web_runtime.cjs');
const {supabaseAdmin: db} = runtime.load('supabaseAdmin');
const projectId = 'e9233112-f0d7-4b35-91bf-2f892844eb30';
const jobId = '9824529b-32f6-4513-a39e-678d496522fc';
(async () => {
 const results = await Promise.all([
  db.from('std_projects').select('*').eq('id',projectId).single(),
  db.from('categories').select('id,upload_channel_id,upload_channel_name,upload_channel_handle').eq('id',13).single(),
  db.from('std_project_assets').select('metadata').eq('id',jobId).single(),
  db.from('publishing_requests').select('id,status').eq('metadata->>project_id','1000003373'),
 ]);
 for(const r of results) if(r.error) throw r.error;
 const [project,category,job,publishing] = results.map(r=>r.data);
 const payload=project.project_payload, rows=payload.subtitles || payload.progress?.subtitles || [];
 const before=JSON.parse(fs.readFileSync('output/project-recovery-e9233112/before-restored-audio-generation.json','utf8'));
 const oldPayload=before.project_payload || before.project?.project_payload || before;
 const audit={projectId,topic:project.topic_queue_id,category,publishing,
  subtitleCount:rows.length,scene37:rows.filter(r=>r.scene_number===37).length,scene38:rows.filter(r=>r.scene_number===38).length,
  pendingAudio:rows.filter(r=>r.restored_audio_pending).length,
  publishMetadataPreserved:JSON.stringify(payload.publish_metadata)===JSON.stringify(oldPayload.publish_metadata),
  thumbnailPreserved:JSON.stringify(payload.thumbnail_design)===JSON.stringify(oldPayload.thumbnail_design),
  audioAssetId:payload.subtitle_source_audio_id,
  ae:{state:job.metadata.state,phase:job.metadata.phase,queueId:job.metadata.auto_render_queue_id,
    outcomes:(job.metadata.results||[]).map(r=>({number:r.number,status:r.status,reason:r.reason,skip_reason:r.skip_reason}))}};
 fs.writeFileSync('output/project-recovery-e9233112/restored-readiness-audit.json',JSON.stringify(audit,null,2));
 console.log(JSON.stringify({...audit,ae:{...audit.ae,outcomes:undefined,counts:audit.ae.outcomes.reduce((c,r)=>(c[r.status]=(c[r.status]||0)+1,c),{})}},null,2));
})().catch(e=>{console.error(e.message);process.exitCode=1});
