const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript')
const root=path.resolve(__dirname,'..'),cache={}
function load(file){if(cache[file])return cache[file];const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:1,target:7}}).outputText)(ex,n=>n.startsWith('./')?load('lib/'+n.slice(2)+'.ts'):require(n));cache[file]=ex;return ex}
const generated=load('lib/stdGeneratedSpeakerGeometry.ts'),geometry=load('lib/stdSpeakerGeometry.ts'),overview=load('lib/stdSpeakerCoordinateOverview.ts')
function fixture(){
 const project={id:'p',topic_queue_id:3373,project_payload:{structure:{main_character:{name:'Mother'}},subtitles:[{scene_number:19,dialogue_kind:'dialogue',dialogue_speaker:'Mother',text:'Hello'}]}}
 const cast=geometry.coordinateCast(project),image={id:'i',project_id:'p',asset_type:'image',status:'uploaded',scene_number:19,metadata:{gcs_bucket:'bucket',gcs_path:'19.png'}}
 const receipt={version:1,source:'local-codex-image-publish',number:19,state:'ready',fingerprint:'receipt',cast,source_bucket:'bucket',source_path:'19.png',source_sha256:'a'.repeat(64),speakers:[{speaker:'Mother',status:'visible',confidence:.99,face_box:[.1,.1,.5,.6],mouth_box:[.25,.4,.32,.44]}]}
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
 const db={from(table){queries.push(table);const data=table==='std_projects'?[f.project]:table==='topics_queue'?[{id:3373,pregenerated_structure:f.structure}]:[f.image];const q={select:()=>q,eq:()=>q,in:()=>q,or:()=>q,order:()=>q,range:()=>q,then:(a,b)=>Promise.resolve({data,error:null}).then(a,b)};return q}}
 const full=await load('lib/stdProjectAssets.ts').loadStdProjectAssets(db,'p','*')
 const status=await load('lib/stdSpeakerCoordinateAssets.ts').loadSpeakerCoordinateAssets(db,['p'])
 assert.deepEqual(full.data,status);assert.equal(full.data.length,2);assert(queries.includes('topics_queue'))
})
