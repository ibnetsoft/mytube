const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {recordedMotionSourceReuse:reuse}=load('lib/stdMotionSourceReuse.ts');
function fixture(){
 const row={text:'spoken line',voice_id:'actor',direction:'calm',kind:'dialogue',scene_number:37,start:20,end:22};
 const project={id:'p',project_payload:{subtitles:[{...row,dialogue_kind:row.kind}]}};
 const audio={id:'new',metadata:{subtitle_timeline:[{...row,start:30,end:32}]}};
 const source={id:'clip',project_id:'p',scene_number:37,asset_type:'video',status:'uploaded',metadata:{ae_mouth_fingerprint:'fp',
  source_audio_id:'old',source_image_id:'image',render_sha256:'a'.repeat(64),timing_mode:'final_voice',voice_synced:true,artifact_ready:true,duration_seconds:2}};
 const assets=[source,{id:'image',project_id:'p',scene_number:37,asset_type:'image',status:'uploaded'},
  {project_id:'p',metadata:{kind:'ae_mouth_job',fingerprint:'fp',input:{audio:{id:'old',metadata:{gcs_bucket:'b',gcs_path:'old.mp3',subtitle_timeline:['large history']}},
   scenes:[{number:37,start:20,end:22,image:{id:'image'}}],subtitles:[row]}}}];
 return {project,audio,source,assets};
}
function check(f){return reuse(f.project,f.source,f.assets,f.audio)}
test('unchanged scene remains a review candidate after another scene changes the global audio ID',()=>{
 const f=fixture(),proof=check(f);assert.ok(proof);assert.equal(proof.current_start,30);assert.equal(proof.start,20);
 assert.equal(proof.audio.id,'old');assert.equal(proof.audio.metadata.subtitle_timeline,undefined);
 assert.match(proof.verification,/pending_pcm_and_output_review/);assert.equal(f.source.metadata.ae_reviewed,undefined);
});
for(const [name,change]of [
 ['different voice',f=>f.audio.metadata.subtitle_timeline[0].voice_id='other'],
 ['changed words',f=>f.project.project_payload.subtitles[0].text='changed'],
 ['changed direction',f=>f.project.project_payload.subtitles[0].direction='angry'],
 ['changed timing',f=>f.audio.metadata.subtitle_timeline[0].end+=.1],
 ['different source image',f=>f.source.metadata.source_image_id='other'],
 ['preview cycle',f=>f.source.metadata.timing_mode='preview_cycle'],
 ['wrong project',f=>f.source.project_id='other'],
 ['missing frozen recording',f=>f.assets.pop()]
])test(name+' cannot reuse a mouth clip',()=>{const f=fixture();change(f);assert.equal(check(f),null)});
test('the frozen motion and media resolver can select the same existing video candidate',()=>{
 const f=fixture();f.project.progress_payload={tts_asset_id:f.audio.id};
 f.project.project_payload.render_settings={motion:{version:1,enabled:true,aspect:'16:9',fps:24,
  scenes:{37:{source:'video',fit:'contain',direction:'keep existing video',effects:[],transition:'cut',
   keys:[{t:0,x:.5,y:.5,scale:1,rotation:0,opacity:100},{t:1,x:.5,y:.5,scale:1,rotation:0,opacity:100}]}}}};
 const media=load('lib/stdSceneMedia.ts');
 assert.equal(media.resolveSceneMedia(f.project,{scene_number:37},[...f.assets,f.audio]).id,'clip');
 f.audio.metadata.subtitle_timeline[0].voice_id='changed';
 assert.throws(()=>media.resolveSceneMedia(f.project,{scene_number:37},[...f.assets,f.audio]),/소스/);
});
