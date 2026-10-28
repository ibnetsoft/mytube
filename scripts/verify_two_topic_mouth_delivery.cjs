const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const rt=require('./std_web_runtime.cjs'),db=rt.load('supabaseAdmin').supabaseAdmin,g=rt.load('gcsStorage');
const targets={3376:[23,37,38,39,47,48,49,57,58,60],3377:[19,20,21,22,23,24,25,26,28,29]};
(async()=>{const results=[];for(const [topic,numbers] of Object.entries(targets)){
 const audit=JSON.parse(fs.readFileSync(path.join(rt.root,'output/two-topic-mouth-audit',topic+'.json'),'utf8'));
 const id=audit.project.id;const {data:project,error}=await db.from('std_projects').select('*').eq('id',id).single();if(error)throw error;
 assert.equal(project.title,audit.project.title);assert.equal(project.submitted_at,audit.project.submitted_at);
 assert.deepEqual(project.project_payload,audit.project.project_payload);assert.deepEqual(project.source_payload,audit.project.source_payload);
 const {data:source,error:se}=await db.from('topics_queue').select('pregenerated_structure').eq('id',Number(topic)).single();if(se)throw se;
 const strip=s=>{s=JSON.parse(JSON.stringify(typeof s==='string'?JSON.parse(s):s));for(const scene of s.scenes||[])if(scene.metadata?.cowork_image_asset)delete scene.metadata.cowork_image_asset.speaker_geometry;return s};
 assert.deepEqual(strip(source.pregenerated_structure),strip(audit.structure));
 const {data:assets,error:ae}=await rt.load('stdProjectAssets').loadStdProjectAssets(db,id,'*');if(ae)throw ae;
 const previews=assets.filter(a=>a.metadata?.kind==='mouth_preview');assert.deepEqual(previews.map(a=>a.scene_number).sort((a,b)=>a-b),numbers);
 const checked=[];for(const number of numbers){
  const local=JSON.parse(fs.readFileSync(path.join(rt.root,'output/codex-local-console/two-topic-mouths',topic,`scene-${String(number).padStart(3,'0')}-speaker-coordinates.json`),'utf8'));
  const item=previews.find(a=>a.scene_number===number),p=item.metadata;assert.equal(p.sha256,local.mouth_preview.sha256);assert.equal(p.voice_synced,false);
  const meta=await g.getGcsObjectMetadata({bucket:p.gcs_bucket,objectPath:p.gcs_path});assert(meta.size>0);assert(meta.contentType.startsWith('video/mp4'));
  let poseImages=0;for(const entry of local.mouth_preparation.entries||[])for(const [pose,asset]of Object.entries(entry.assets||{})){
   const m=await g.getGcsObjectMetadata({bucket:asset.bucket||asset.gcs_bucket,objectPath:asset.path||asset.gcs_path});assert(m.size>0);poseImages++;
  }
  checked.push({scene:number,preview_saved:true,gcs_bytes:meta.size,pose_images:poseImages,preserve_original:!!p.preserve_original});
 }
 results.push({topic:Number(topic),project_id:id,title:project.title,preview_count:previews.length,title_preserved:true,submission_unchanged:true,scenes:checked});
 console.log(JSON.stringify(results.at(-1)));
 }
 fs.writeFileSync(path.join(rt.root,'output/codex-local-console/two-topic-mouths/delivery-verification.json'),JSON.stringify(results,null,2));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
