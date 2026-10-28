const rt=require('../scripts/std_web_runtime.cjs'),fs=require('node:fs'),path=require('node:path');
(async()=>{const base='D:/AIRStudio/verification/production-submit-20261024',db=rt.load('supabaseAdmin').supabaseAdmin,reports=[];
for(const mode of ['normal','short']){const t=JSON.parse(fs.readFileSync(`${base}/${mode}/test.json`));const q=await db.from('std_project_assets').select('metadata').eq('id',t.submission.job_id).single();if(q.error)throw q.error;const m=q.data.metadata,s=JSON.parse(m.input.snapshot_json);fs.writeFileSync(`${base}/${mode}/job.json`,JSON.stringify(m,null,2));
const queue=await db.from('remote_render_queue').select('id,status,progress,result_file_id').eq('id',t.submission.job_id);if(queue.error)throw queue.error;
reports.push({mode,project_id:t.project_id,job_id:t.submission.job_id,state:m.state,phase:m.phase,progress:m.progress,error:m.error,source_kinds:s.scenes.map(x=>x.source_kind),execution_policy:s.execution_policy,results:(m.results||[]).map(x=>({number:x.number,review:x.review,video_playback_policy:x.video_playback_policy,output:x.output})),final:m.final||null,review:m.review||null,render_queue:queue.data});
if(m.final?.gcs_path){const obj=await rt.load('gcsStorage').getGcsObjectMetadata({bucket:m.final.gcs_bucket,objectPath:m.final.gcs_path});reports.at(-1).uploaded_object={size:obj.size,contentType:obj.contentType};}
}
fs.writeFileSync(`${base}/status.json`,JSON.stringify(reports,null,2));console.log(JSON.stringify(reports));
})().catch(e=>{console.error(e.message);process.exitCode=1});
