const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('../node_modules/typescript')
const load=require('./load-ts-module.cjs'), identity=load('lib/stdContentIdentity.ts')
function renderer(){
 const ex={}; const source=fs.readFileSync('lib/stdRenderQueue.ts','utf8')+'\nexport const previewForTest = buildGcsRenderConfig;'
 new Function('exports','require',ts.transpile(source,{module:1,target:7}))(ex,name=>{
  if(name==='crypto')return require('crypto')
  if(name.includes('stdContentIdentity'))return identity
  if(name.includes('stdSceneMedia'))return load('lib/stdSceneMedia.ts')
  if(name.includes('stdAudioAnchors'))return load('lib/stdAudioAnchors.ts')
  if(name.includes('stdNonverbal'))return {isNonverbalProject:()=>false}
  if(name.includes('stdLipSync'))return {lipSyncEnabled:()=>false,reviewedLipSyncAssets:()=>new Map(),lipSyncSceneStarts:()=>[0]}
  if(name.includes('stdAeMouth'))return {reviewedAeMouthAssets:()=>new Map()}
  if(name.includes('stdComic'))return {isComicProject:()=>false,comicSettingsForProject:()=>({panels:{},mode:'classic'}),selectComicMedia:(_m,image,video)=>image||video}
  if(name.includes('stdSpeechGain'))return {subtitleGain:()=>1}
  if(name.includes('stdSfxCues'))return {resolveSfxCues:()=>[]}
  if(name.includes('stdAudioMix'))return {audioAssetRole:a=>a.asset_type}
  if(name.includes('stdSceneMotion'))return {sceneMotion:()=> 'none',sceneMotionSpeed:()=>1}
  if(name.includes('stdVideoTail'))return {reviewedVideoTail:(_scene,source)=>source}
  if(name.includes('stdTemplateOverlayPng'))return {templateOverlayPng:async()=>null}
  if(name.includes('gcsStorage'))return {gcsBucketName:()=> 'bucket',isGcsConfiguredAsync:async()=>false}
  return {}
 })
 return ex.previewForTest
}
function fixture(){const rows=[{text:'原本。',voice_id:'v',start_num:0,end_num:8,scene_number:19}]
 const p={id:'p',topic_queue_id:3373,project_payload:{script:'原本。',subtitles:rows,voice_id:'v',settings:{worker_tts_enabled:true}},progress_payload:{tts_asset_id:'audio'}}
 const scene={id:'scene',scene_number:19,image_prompt:'old girl'}
 const audio={id:'audio',project_id:'p',asset_type:'audio',status:'uploaded',file_name:'original.mp3',metadata:{gcs_bucket:'bucket',gcs_path:'std-projects/p/original.mp3',subtitle_timeline:rows,duration_seconds:8}}
 const image={id:'image',project_id:'p',scene_id:'scene',scene_number:19,asset_type:'image',status:'assigned',file_name:'original.png',metadata:{gcs_bucket:'bucket',gcs_path:'topics/3373/image.png'}}
 return {p,scene,audio,image}
}
test('final GCS composition uses the same frozen comic neighbor source selector',async()=>{
 const f=fixture()
 f.p.project_payload.submission_pipeline_version=2
 f.p.project_payload.render_settings={comic:{version:1,mode:'moving_comic',panels:{'19':{motion:'still'}}}}
 const video={...f.image,id:'video',asset_type:'video',file_name:'generated.mp4',metadata:{gcs_bucket:'bucket',gcs_path:'different-video.mp4'}}
 const selected=load('lib/stdSceneMedia.ts').resolveSceneMedia(f.p,f.scene,[video,f.image,f.audio])
 const config=await renderer()(f.p,[f.scene],[video,f.image,f.audio],1000003373)
 const visual=config.asset_manifest.files.find(item=>['image','video'].includes(item.asset_type))
 assert.equal(selected.id,'image')
 assert.equal(visual.content_identity.asset_id,selected.id)
 assert.equal(visual.asset_type,'image')
})
test('real render config binds original audio, scene assets and duration and suppresses TTS without AE',async()=>{
 const f=fixture(),newer={...f.audio,id:'wrong',file_name:'expanded.mp3',metadata:{...f.audio.metadata,duration_seconds:34,subtitle_timeline:[{...f.audio.metadata.subtitle_timeline[0],end_num:34}]}}
 const config=await renderer()(f.p,[f.scene],[newer,f.image,f.audio],1000003373)
 assert.equal(config.audio_duration,8);assert.equal(config.worker_tts,null)
 const audio=config.asset_manifest.files.find(f=>f.asset_type==='audio'),visual=config.asset_manifest.files.find(f=>f.asset_type==='image')
 assert.equal(audio.content_identity.asset_id,'audio');assert.equal(audio.file_name,'original.mp3')
 assert.equal(visual.content_identity.asset_id,'image');assert.equal(visual.content_identity.scene_id,'scene')
})
test('real render config rejects expanded scripts and cross-topic visuals before creating a queue',async()=>{
 let f=fixture();f.p.project_payload.script='別の長い話。'
 await assert.rejects(()=>renderer()(f.p,[f.scene],[f.audio,f.image],1),/大本|대본/)
 f=fixture();f.image.metadata.gcs_path='topics/123/image.png'
 await assert.rejects(()=>renderer()(f.p,[f.scene],[f.audio,f.image],1),/토픽 번호/)
})
test('disabled mouth effects never make an old mouth output eligible as an original scene video',async()=>{
 const f=fixture(),wrong={id:'old-mouth',project_id:'p',scene_number:19,asset_type:'video',status:'uploaded',metadata:{ae_mouth_fingerprint:'old',source_audio_id:'other',gcs_path:'old.mp4'}}
 const config=await renderer()(f.p,[f.scene],[wrong,f.audio,f.image],1)
 assert.equal(config.asset_manifest.files.find(f=>f.asset_type==='image').content_identity.asset_id,'image')
 assert.equal(config.asset_manifest.files.some(f=>f.asset_type==='video'),false)
})
