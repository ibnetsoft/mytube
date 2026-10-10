const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
const cache={};function load(file){if(cache[file])return cache[file];const ex={};cache[file]=ex;new Function('exports','require',ts.transpile(fs.readFileSync(`lib/${file}.ts`,'utf8'),{module:1,target:7}))(ex,name=>name==='./stdComic'?{isComicProject:p=>p.project_payload?.comic_settings?.mode==='comic'}:name.startsWith('./')?load(name.slice(2)):require(name));return ex;}
const lib=load('stdAeMouth');
function fixture(){
 const subtitles=[{text:'설명',voice_id:'n',scene_number:18,start:0,end:1,dialogue_kind:'narration'},
  {text:'어머니',voice_id:'a',scene_number:19,start:1,end:2,dialogue_kind:'dialogue',dialogue_speaker:'소녀'},
  {text:'끝',voice_id:'n',scene_number:20,start:3,end:4,dialogue_kind:'narration'}];
 const project={id:'p',project_payload:{subtitles,ae_mouth:{enabled:true},structure:{scenes:[{scene_number:19,scene_text:'어머니',image_prompt:'girl'}]}}};
 const scenes=[18,19,20].map(n=>({scene_number:n,scene_text:n===19?'어머니':'설명'}));
 const assets=[{id:'audio',asset_type:'audio',status:'assigned',created_at:'2026-10-05',metadata:{subtitle_timeline:subtitles.map(s=>({...s}))}},
  ...scenes.map(s=>({id:`image${s.scene_number}`,scene_number:s.scene_number,asset_type:'image',status:'assigned',created_at:'2026-10-05',metadata:{gcs_path:'image.png'}}))];
 return {project,scenes,assets};
}
test('snapshot covers only still scenes 19 onward with finalized voice timing',()=>{
 const f=fixture(),r=lib.aeMouthInput(f.project,f.scenes,f.assets);
 assert.deepEqual(r.input.scenes.map(s=>s.number),[19,20]);assert.equal(r.input.scenes[0].start,1);assert.equal(r.input.scenes[0].end,3);
 assert.equal(lib.aeMouthApplicable({...f.project,project_payload:{comic_settings:{mode:'comic'}}},f.scenes),false);
 assert.equal(lib.aeMouthApplicable(f.project,[{scene_number:18}]),false);
});
test('changed source, voice, cast, classification or AE direction invalidates fingerprint',()=>{
 const original=fixture(),hash=lib.aeMouthInput(original.project,original.scenes,original.assets).fingerprint;
 for(const mutate of [f=>f.assets[0].id='new-voice',f=>f.assets[2].id='new-image',f=>f.project.project_payload.structure.main_character={name:'different'},f=>f.project.project_payload.subtitles[1].dialogue_speaker='다른 인물',f=>f.project.project_payload.structure.scenes[0].ae_motion_plan={enabled:true,preset:'different'}]){
  const f=fixture();mutate(f);assert.notEqual(lib.aeMouthInput(f.project,f.scenes,f.assets).fingerprint,hash);
 }
 const f=fixture();f.project.project_payload.subtitles[1].text='변경';assert.throws(()=>lib.aeMouthInput(f.project,f.scenes,f.assets),/TTS/);
});
test('replacing a submitted dialogue clip invalidates the old AE job',()=>{
 const f=fixture();f.project.project_payload.subtitles[0].dialogue_kind='dialogue';f.project.project_payload.subtitles[0].dialogue_speaker='소녀';
 f.assets.push({id:'old-video',project_id:'p',asset_type:'video',status:'assigned',scene_number:18,created_at:'2026-10-05',metadata:{gcs_path:'old.mp4'}});
 const snapshot=lib.aeMouthInput(f.project,f.scenes,f.assets);
 f.assets.push({id:'old-job',asset_type:'other',status:'uploaded',created_at:'2026-10-06',metadata:{kind:'ae_mouth_job',state:'queued',...snapshot}});
 assert.equal(lib.currentAeMouthJob(f.project,f.scenes,f.assets).id,'old-job');
 f.assets.find(a=>a.id==='old-video').status='replaced';
 f.assets.push({id:'new-video',project_id:'p',asset_type:'video',status:'assigned',scene_number:18,created_at:'2026-10-09',metadata:{gcs_path:'new.mp4'}});
 assert.equal(lib.currentAeMouthJob(f.project,f.scenes,f.assets),null);
 assert.equal(lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes[0].original_video.id,'new-video');
});
test('render gate accepts reviewed current assets, rejects unreviewed and stale output',()=>{
 const f=fixture(),fingerprint=lib.aeMouthInput(f.project,f.scenes,f.assets).fingerprint;
 const output={id:'output',asset_type:'video',status:'uploaded',scene_number:19,metadata:{ae_mouth_fingerprint:fingerprint,ae_reviewed:true,timing_locked:true,duration_seconds:2}};
 const job={id:'job',asset_type:'other',status:'uploaded',metadata:{kind:'ae_mouth_job',fingerprint,state:'review_pending',results:[{number:19,status:'approved',asset_id:'output',duration:2},{number:20,status:'skipped'}]}};
 f.assets.push(output,job);assert.throws(()=>lib.reviewedAeMouthAssets(f.project,f.scenes,f.assets));
 job.metadata.state='reviewed';assert.equal(lib.reviewedAeMouthAssets(f.project,f.scenes,f.assets).get(19).id,'output');
 output.metadata.ae_reviewed=false;assert.throws(()=>lib.reviewedAeMouthAssets(f.project,f.scenes,f.assets));
});
test('newer retry and newer audio are selected regardless of caller ordering',()=>{
 const f=fixture(),fingerprint=lib.aeMouthInput(f.project,f.scenes,f.assets).fingerprint;
 const job=state=>({id:state,status:'uploaded',asset_type:'other',metadata:{kind:'ae_mouth_job',fingerprint,state}});
 f.assets.push({...job('failed'),created_at:'2026-10-01'},{...job('queued'),created_at:'2026-10-06'});
 assert.equal(lib.currentAeMouthJob(f.project,f.scenes,f.assets).id,'queued');
});

test('saved geometry is reused only for the same image, cast and assigned speaker',()=>{
 const f=fixture(),cast={main:{},supporting:[],scene_cast:[]};
 const regions={number:19,image_id:'image19',source_path:'image.png',source_sha256:'a'.repeat(64),speakers:[{speaker:'소녀',status:'visible',confidence:.99,mouth_box:[.4,.4,.45,.43],face_box:[.2,.2,.7,.7]}]};
 const metadata={kind:'ae_speaker_coordinates',state:'ready',input:{cast_key:JSON.stringify(cast)},results:[regions]};
 f.assets.unshift({id:'coords',asset_type:'other',status:'uploaded',metadata});
 assert.deepEqual(lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes[0].speaker_regions,{...regions,origin:'ai'});
 metadata.input.cast_key='changed';assert.equal(lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes[0].speaker_regions,null);
 metadata.input.cast_key=JSON.stringify(cast);regions.image_id='other';assert.equal(lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes[0].speaker_regions,null);
 regions.image_id='image19';regions.speakers[0].speaker='other';assert.equal(lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes[0].speaker_regions,null);
});


test('user-confirmed coordinates reach the render snapshot without an AI job',()=>{
 const f=fixture(),geometry=load('stdSpeakerGeometry'),scene=geometry.coordinateScenes(f.project,f.assets)[0];
 const result={number:19,image_id:'image19',source_path:'image.png',source_sha256:'a'.repeat(64),
  speakers:[{speaker:'소녀',status:'visible',confidence:1,face_box:[.2,.2,.7,.7],mouth_box:[.4,.4,.45,.43]}]};
 f.assets.push({id:'manual',asset_type:'other',status:'uploaded',metadata:{kind:'speaker_coordinate_confirmation',scene_key:scene.key,results:[result]}});
 const snapshot=lib.aeMouthInput(f.project,f.scenes,f.assets);
 assert.equal(snapshot.input.scenes[0].speaker_regions.origin,'user');
 assert.deepEqual(snapshot.input.scenes[0].speaker_regions.speakers,result.speakers);
});

test('partial coordinates remain available to AE when another scene needs review',()=>{
 const f=fixture(),cast={main:{},supporting:[],scene_cast:[]};
 const result={number:19,image_id:'image19',source_path:'image.png',source_sha256:'a'.repeat(64),speakers:[{speaker:'소녀',status:'visible',confidence:.99,face_box:[.2,.2,.7,.7],mouth_box:[.4,.4,.45,.43]}]};
 const metadata={kind:'ae_speaker_coordinates',state:'needs_review',input:{cast_key:JSON.stringify(cast)},results:[result],failures:[{number:20,error:'uncertain'}]};
 f.assets.push({id:'partial',asset_type:'other',status:'uploaded',metadata});
 for(const state of ['needs_review','processing','queued']){
  metadata.state=state;
  const scenes=lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes;
  assert.equal(scenes[0].speaker_regions.image_id,'image19',state);
  assert.equal(scenes[1].speaker_regions,null);
 }
});

test('newly analyzed scenes do not discard AE work but corrected used coordinates do',()=>{
 const f=fixture(),cast={main:{},supporting:[],scene_cast:[]};
 f.project.project_payload.subtitles[2].dialogue_kind='dialogue';
 f.project.project_payload.subtitles[2].dialogue_speaker='소녀';
 const result=n=>({number:n,image_id:`image${n}`,source_path:'image.png',source_sha256:'a'.repeat(64),speakers:[{speaker:'소녀',status:'visible',confidence:.99,face_box:[.2,.2,.7,.7],mouth_box:[.4,.4,.45,.43]}]});
 const metadata={kind:'ae_speaker_coordinates',state:'processing',input:{cast_key:JSON.stringify(cast)},results:[result(19)]};
 f.assets.push({id:'coords',asset_type:'other',status:'uploaded',metadata});
 const snapshot=JSON.parse(JSON.stringify(lib.aeMouthInput(f.project,f.scenes,f.assets)));
 f.assets.push({id:'ae',asset_type:'other',status:'uploaded',metadata:{kind:'ae_mouth_job',state:'direction_pending',...snapshot}});
 metadata.results.push(result(20));
 assert.equal(lib.currentAeMouthJob(f.project,f.scenes,f.assets).id,'ae');
 metadata.results[0].speakers[0].mouth_box=[.42,.4,.47,.43];
 assert.equal(lib.currentAeMouthJob(f.project,f.scenes,f.assets),null);
});

 test('video dialogue before scene 19 enters tracking snapshot and invalidates on clip changes',()=>{
 const f=fixture();f.project.project_payload.subtitles[0].dialogue_kind='dialogue';f.project.project_payload.subtitles[0].dialogue_speaker='소녀';
 const video={id:'video18',scene_number:18,asset_type:'video',status:'assigned',metadata:{gcs_path:'original.mp4'}};f.assets.push(video);
 const before=lib.aeMouthInput(f.project,f.scenes,f.assets);
 assert.equal(before.input.version,2);assert.deepEqual(before.input.scenes.map(s=>s.number),[18,19,20]);
 assert.equal(before.input.scenes[0].original_video.id,'video18');
 video.id='new-video';assert.notEqual(lib.aeMouthInput(f.project,f.scenes,f.assets).fingerprint,before.fingerprint);
 });
 test('video narration remains excluded and missing dialogue video cannot silently use a still',()=>{
 const f=fixture();f.assets.push({id:'video18',scene_number:18,asset_type:'video',status:'assigned',metadata:{gcs_path:'original.mp4'}});
 assert.deepEqual(lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes.map(s=>s.number),[19,20]);
 f.project.project_payload.subtitles[0].dialogue_kind='dialogue';f.project.project_payload.subtitles[0].dialogue_speaker='소녀';f.assets.pop();
 assert.throws(()=>lib.aeMouthInput(f.project,f.scenes,f.assets),/원본 영상/);
 });

 test('background audio is never substituted for finalized TTS',()=>{
 const f=fixture();f.assets.unshift({id:'bgm',asset_type:'audio',status:'assigned',created_at:'2026-10-09',metadata:{audio_role:'background'}});
 assert.equal(lib.aeMouthInput(f.project,f.scenes,f.assets).input.audio.id,'audio');
 });
test('generation-time coordinates reach AE submission with original asset metadata intact',()=>{
 const f=fixture(),geometry=load('stdSpeakerGeometry'),generated=load('stdGeneratedSpeakerGeometry');
 f.assets.forEach(a=>a.project_id='p');
 const image=f.assets.find(a=>a.scene_number===19),speakers=[{speaker:'소녀',status:'visible',confidence:.99,face_box:[.1,.1,.5,.6],mouth_box:[.25,.4,.32,.44]}];
 const structure={scenes:[{scene_number:19,metadata:{cowork_image_asset:{speaker_geometry:{source:'local-codex-image-publish',number:19,state:'ready',fingerprint:'ready',cast:geometry.coordinateCast(f.project),source_bucket:'air-studio-prod',source_path:'image.png',source_sha256:'a'.repeat(64),speakers}}}}]};
 const assets=[...f.assets,...generated.generatedSpeakerAssets(f.project,structure,f.assets)];
 const input=lib.aeMouthInput(f.project,f.scenes,assets).input;
 assert.deepEqual(input.scenes[0].speaker_regions.speakers,speakers);
 assert.deepEqual(input.scenes[0].image,{id:image.id,metadata:image.metadata});
});
test('confirmed eye blink plan is source-bound and invalidates stale AE work',()=>{
 const f=fixture(),plan={id:'blink',asset_type:'other',status:'uploaded',scene_number:19,created_at:'2026-10-10',metadata:{
  kind:'eye_blink_confirmation',state:'confirmed',version:1,image_id:'image19',source_bucket:'b',source_path:'image.png',source_sha256:'a'.repeat(64),
  character:'소녀',left_eye_box:[.3,.3,.34,.33],right_eye_box:[.4,.3,.44,.33],interval_seconds:4,confirmed_by:'user'}};
 f.assets.unshift(plan);const before=lib.aeMouthInput(f.project,f.scenes,f.assets);
 assert.equal(before.input.scenes[0].eye_blink.id,'blink');assert.equal(before.input.scenes[0].eye_blink.character,'소녀');
 f.assets.unshift({...plan,id:'new-blink',created_at:'2026-10-11',metadata:{...plan.metadata,interval_seconds:6}});
 assert.notEqual(lib.aeMouthInput(f.project,f.scenes,f.assets).fingerprint,before.fingerprint);
});
test('approved layered PSD is frozen into the same eye and mouth render snapshot',()=>{
 const f=fixture(),source=f.project.project_payload.structure.scenes[0];
 source.ae_effect_plan={enabled:true,template:'parallax_layered_scene'};
 source.metadata={psd_layer_asset:{qa_status:'approved',gcs_bucket:'layers',gcs_path:'p/scene-019.psd',sha256:'b'.repeat(64),layers:['background','character','foreground']}};
 const before=lib.aeMouthInput(f.project,f.scenes,f.assets);
 assert.equal(before.input.scenes[0].layered_source.metadata.gcs_path,'p/scene-019.psd');
 source.metadata.psd_layer_asset.sha256='c'.repeat(64);
 assert.notEqual(lib.aeMouthInput(f.project,f.scenes,f.assets).fingerprint,before.fingerprint);
 source.metadata.psd_layer_asset.qa_status='pending_visual_review';
 assert.equal(lib.aeMouthInput(f.project,f.scenes,f.assets).input.scenes[0].layered_source,null);
});
