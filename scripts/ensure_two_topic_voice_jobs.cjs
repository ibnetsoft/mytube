const rt=require('./std_web_runtime.cjs');
(async()=>{const db=rt.load('supabaseAdmin').supabaseAdmin;for(const id of ['05e173f1-46a4-42e6-b543-6d7ba4458368','dcf670cc-ace7-4c3f-861f-186441724d08']){
 const p=await db.from('std_projects').select('*').eq('id',id).single();if(p.error)throw p.error;
 const [s,a,source]=await Promise.all([db.from('std_project_scenes').select('*').eq('project_id',id).order('scene_number'),db.from('std_project_assets').select('*').eq('project_id',id).in('status',['uploaded','assigned']).or('asset_type.in.(audio,image,video),metadata->>kind.eq.ae_mouth_job').limit(1000),db.from('topics_queue').select('pregenerated_structure').eq('id',Number(p.data.topic_queue_id)).single()]);if(s.error||a.error||source.error)throw s.error||a.error||source.error;
 const structure=typeof source.data.pregenerated_structure==='string'?JSON.parse(source.data.pregenerated_structure):source.data.pregenerated_structure;
 a.data.push(...rt.load('stdGeneratedSpeakerGeometry').generatedSpeakerAssets(p.data,structure,a.data));
 const audio=a.data.find(x=>x.asset_type==='audio'&&x.metadata?.subtitle_timeline?.length);
 if(!audio){console.log(JSON.stringify({id,state:'waiting_for_final_voice'}));continue}
 const job=await rt.load('stdSubmissionPipeline').ensureSyncedMouthPreview(p.data,s.data,a.data);
 console.log(JSON.stringify({id,audio_id:audio.id,job_id:job?.id,state:job?.metadata?.state,scope:job?.metadata?.input?.mouth_work_scene_numbers,scenes:job?.metadata?.input?.scenes?.map(x=>({number:x.number,start:x.start,end:x.end,geometry:!!x.speaker_regions}))}));
}})().catch(e=>{console.error(e.stack);process.exitCode=1});
