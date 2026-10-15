const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript')
const root=path.resolve(__dirname,'..'),cache={}
function load(file){if(cache[file])return cache[file];const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:1,target:7}}).outputText)(ex,n=>n.startsWith('./')?load('lib/'+n.slice(2)+'.ts'):require(n));cache[file]=ex;return ex}
const generated=load('lib/stdGeneratedSpeakerGeometry.ts'),geometry=load('lib/stdSpeakerGeometry.ts'),overview=load('lib/stdSpeakerCoordinateOverview.ts')
function fixture(){
 const project={id:'p',topic_queue_id:3373,project_payload:{structure:{main_character:{name:'Mother'}},subtitles:[{scene_number:19,dialogue_kind:'dialogue',dialogue_speaker:'Mother',text:'Hello'}]}}
 const cast=geometry.coordinateCast(project),image={id:'i',project_id:'p',asset_type:'image',status:'uploaded',scene_number:19,metadata:{gcs_bucket:'bucket',gcs_path:'19.png'}}
 const receipt={version:1,source:'local-codex-image-publish',number:19,state:'ready',fingerprint:'receipt',cast,source_bucket:'bucket',source_path:'19.png',source_sha256:'a'.repeat(64),speakers:[{speaker:'Mother',status:'visible',confidence:.99,face_box:[.1,.1,.5,.6],mouth_box:[.25,.4,.32,.44]}]}
 receipt.speakers[0].mouth_geometry={version:2,source_sha256:receipt.source_sha256,orientation:'frontal',pitch:'level',mouth_visibility:'clear',render_policy:'animate',evidence:'fixture lips',face_outline:[[.1,.1],[.5,.1],[.5,.5],[.3,.6],[.1,.5]],landmarks:{nose_tip:[.285,.28],chin:[.285,.55],lip_left:[.26,.42],lip_right:[.31,.42],lip_center:[.285,.42]},review:{passed:true,reason:'fixture checked',proof:'annotated-face-crop-v4'}}
 const structure={scenes:[{scene_number:19,metadata:{cowork_image_asset:{speaker_geometry:receipt}}}]}
 return{project,cast,image,receipt,structure}
}
test('generated receipt feeds status and geometry without modifying original image metadata',()=>{
 const f=fixture();f.receipt.cast={scene_cast:f.cast.scene_cast,supporting:f.cast.supporting,main:f.cast.main};const assets=[f.image,...generated.generatedSpeakerAssets(f.project,f.structure,[f.image])]
 const scene=geometry.coordinateScenes(f.project,assets)[0],result=geometry.savedSpeakerGeometry(assets,f.cast,scene)
 assert.equal(result.image_id,'i');assert.deepEqual(result.speakers,f.receipt.speakers)
 assert.equal(overview.speakerCoordinateOverview(f.project,assets).completed,1)
 assert.deepEqual(f.image.metadata,{gcs_bucket:'bucket',gcs_path:'19.png'})
 const manual={status:'uploaded',metadata:{kind:'speaker_coordinate_confirmation',scene_key:scene.key,results:[result]}}
 assert.equal(geometry.savedSpeakerGeometry([...assets,manual],f.cast,scene).origin,'user')
 assert.equal(geometry.savedSpeakerGeometry(assets,{...f.cast,main:{name:'different'}},scene),null)
 scene.rows[0].speaker='Other';assert.equal(geometry.savedSpeakerGeometry(assets,f.cast,scene),null)
})
test('replacement images never inherit coordinates; failed generation remains visible for review',()=>{
 const f=fixture();f.image.metadata.gcs_path='replacement.png'
 assert.deepEqual(generated.generatedSpeakerAssets(f.project,f.structure,[f.image]),[])
 f.image.metadata.gcs_path='19.png';f.receipt.state='needs_review';f.receipt.error='Occluded mouth'
 const assets=[f.image,...generated.generatedSpeakerAssets(f.project,f.structure,[f.image])]
 const info=overview.speakerCoordinateOverview(f.project,assets)
 assert.equal(info.completed,0);assert.equal(info.failed,1);assert.equal(info.scenes[0].error,'Occluded mouth')
})
test('validated directed blink becomes a source-bound virtual confirmation asset',()=>{
 const f=fixture();f.receipt.eye_blink={state:'ready',character:'Mother',reason:'reaction pause',
  left_eye_box:[.2,.2,.24,.23],right_eye_box:[.3,.2,.34,.23],
  cues:[{at_seconds:2.4,duration_seconds:.11,type:'single'}]}
 const assets=generated.generatedSpeakerAssets(f.project,f.structure,[f.image])
 const blink=assets.find(a=>a.metadata.kind==='eye_blink_confirmation')
 assert.equal(blink.id,'generated-eye-blink:i:receipt');assert.equal(blink.metadata.version,2)
 assert.equal(blink.metadata.character,'Mother');assert.deepEqual(blink.metadata.cues,f.receipt.eye_blink.cues)
 assert.equal(blink.metadata.image_id,'i');assert.equal(blink.metadata.source_path,'19.png')
})
test('submission and coordinate loaders read latest topic receipts for existing projects',async()=>{
 const f=fixture(),queries=[]
 const db={rpc:async()=>{queries.push('compact-context');return{data:[{...f.project,generated_structure:f.structure}],error:null}},from(table){queries.push(table);const data=table==='std_projects'?[f.project]:table==='topics_queue'?[{id:3373,pregenerated_structure:f.structure}]:[f.image];const q={select:()=>q,eq:()=>q,in:()=>q,or:()=>q,order:()=>q,range:()=>q,then:(a,b)=>Promise.resolve({data,error:null}).then(a,b)};return q}}
 const full=await load('lib/stdProjectAssets.ts').loadStdProjectAssets(db,'p','*')
 const status=await load('lib/stdSpeakerCoordinateAssets.ts').loadSpeakerCoordinateAssets(db,['p'])
 assert.deepEqual(full.data,status);assert.equal(full.data.length,2);assert(queries.includes('compact-context'));assert(!queries.includes('topics_queue'));assert(!queries.includes('std_projects'))
})

test('compact receipts retain current-cast validation without repeating the cast',()=>{
 const f=fixture();delete f.receipt.cast;f.receipt.cast_matches=true
 const assets=[f.image,...generated.generatedSpeakerAssets(f.project,f.structure,[f.image])]
 assert.equal(overview.speakerCoordinateOverview(f.project,assets).completed,1)
 f.receipt.cast_matches=false
 const stale=[f.image,...generated.generatedSpeakerAssets(f.project,f.structure,[f.image])]
 assert.equal(overview.speakerCoordinateOverview(f.project,stale).completed,0)
})

test('empty worker scope survives assignment and does not request coordinates',()=>{
 const f=fixture();f.receipt.state='not_required';f.receipt.mouth_work_selection={policy:{enabled:false,start_scene:19,max_dialogue_scenes:10},scene_numbers:[]};
 const assets=[f.image,...generated.generatedSpeakerAssets(f.project,f.structure,[f.image])];
 assert.equal(geometry.coordinateScenes(f.project,assets).length,0);
 assert.deepEqual(assets.find(a=>a.metadata.kind==='mouth_work_selection').metadata.scene_numbers,[]);
});
test('GCS preview is source-bound and kept separate from final voice clips',()=>{
 const f=fixture();f.receipt.mouth_preview={state:'ready',source_sha256:f.receipt.source_sha256,gcs_path:'preview.mp4',url:'/api/std/assets/gcs-file?path=preview.mp4',sha256:'b'.repeat(64),voice_synced:false};
 const assets=generated.generatedSpeakerAssets(f.project,f.structure,[f.image]);
 assert.equal(assets.find(a=>a.metadata.kind==='mouth_preview').metadata.voice_synced,false);
 assert.equal(geometry.coordinateVideo(assets,19),undefined);
 f.receipt.mouth_preview.source_sha256='c'.repeat(64);
 assert(!generated.generatedSpeakerAssets(f.project,f.structure,[f.image]).some(a=>a.metadata.kind==='mouth_preview'));
});
