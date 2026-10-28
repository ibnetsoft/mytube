const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const rt=require('./std_web_runtime.cjs'),db=rt.load('supabaseAdmin').supabaseAdmin;
const directory=path.resolve('output/codex-local-console/mouth-data-nine-3373');
(async()=>{
 const data=JSON.parse(fs.readFileSync(path.join(directory,'mouth-data.json'),'utf8'));
 const numbers=[22,23,24,25,30,31,32,33,34];
 if(JSON.stringify(data.scenes.map(s=>s.number))!==JSON.stringify(numbers))throw Error('Requested scene scope differs');
 const project=await db.from('std_projects').select('id,project_payload').eq('id',data.project_id).single();if(project.error)throw project.error;
 const cast=rt.load('stdSpeakerGeometry').coordinateCast(project.data);
 const fingerprint=crypto.createHash('sha256').update(JSON.stringify({cast,scenes:data.scenes})).digest('hex');
 const existing=await db.from('std_project_assets').select('id,metadata').eq('project_id',data.project_id).eq('file_name','mouth-data-22-25-30-34.json').maybeSingle();if(existing.error)throw existing.error;
 if(existing.data&&existing.data.metadata.fingerprint!==fingerprint)throw Error('Previous saved geometry differs; preserve it before replacing');
 const metadata={kind:'ae_speaker_coordinates',state:'ready',fingerprint,source:'codex_direct_source_image_measurement',automatic:false,
  input:{cast_key:JSON.stringify(cast),cast,scenes:data.scenes.map(s=>({number:s.number,image:{id:s.image_id},rows:s.speakers.map(p=>({speaker:p.speaker}))}))},
  results:data.scenes,failures:[],geometry_version:2,geometry_review_proof:'annotated-face-crop-v4',requested_scene_numbers:numbers,
  video_tracking_verified:false,mouth_image_generation_requested:false,render_requested:false};
 let id=existing.data?.id;
 if(!id){const saved=await db.from('std_project_assets').insert({project_id:data.project_id,asset_type:'other',status:'uploaded',file_name:'mouth-data-22-25-30-34.json',mime_type:'application/json',metadata}).select('id').single();if(saved.error)throw saved.error;id=saved.data.id;}
 const check=await db.from('std_project_assets').select('id,metadata').eq('id',id).single();if(check.error)throw check.error;
 if(check.data.metadata.results.length!==9||check.data.metadata.results.some(s=>s.state!=='ready'))throw Error('Saved geometry readback differs');
 const receipt={asset_id:id,scenes:numbers,mouths:check.data.metadata.results.reduce((n,s)=>n+s.speakers.length,0),saved:true,source_images_only:true,rendered:false};
 fs.writeFileSync(path.join(directory,'saved-receipt.json'),JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));
})().catch(e=>{console.error(e.message);process.exitCode=1});
