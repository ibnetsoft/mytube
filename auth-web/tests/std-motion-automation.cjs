const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),crypto=require('crypto')
function fixture(mode='ae_only') {
 const calls={models:0,voice:0,rpc:[]},exports={}
 const project={id:'qa-project',updated_at:'now',employee_email:'owner@test',project_payload:{render_settings:{motion:{version:1,enabled:true,aspect:'9:16',fps:24,scenes:{},automation:{mode,max_ai_clips:1,max_ai_seconds:5}}},subtitles:[{text:'Final voice',scene_number:1,start:0,end:20}]}}
 const audio={id:'voice',asset_type:'audio',status:'uploaded',metadata:{gcs_path:'voice.wav',subtitle_timeline:[{start:0,end:20}]}},image={id:'image',asset_type:'image',scene_number:1,status:'uploaded',created_at:'now',metadata:{gcs_path:'source.png'}}
 new Function('exports','require',ts.transpileModule(fs.readFileSync('lib/stdMotionAutomation.ts','utf8'),{compilerOptions:{module:1,target:9}}).outputText)(exports,name=>{
  if(name==='crypto')return crypto
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:{rpc:async(name,args)=>{calls.rpc.push({name,args});return {data:{job_id:'queued'},error:null}}}}
  if(name.includes('stdMotionStudio'))return {motionForProject:p=>p.project_payload.render_settings.motion}
  if(name.includes('stdAeScenePreparation'))return {aeSceneSources:()=>new Map()}
  if(name.includes('stdContentIdentity'))return {selectNarrationAsset:()=>audio}
  if(name.includes('stdLipSync'))return {lipSyncPlan:()=>{calls.voice++},lipSyncSceneStarts:()=>[.005],reviewedLipSyncAssets:()=>new Map()}
  if(name.includes('stdSceneMedia'))return {storageSourceForAsset:a=>a.metadata.gcs_path}
  if(name.includes('stdAudioMix'))return {backgroundWindow:()=>({valid:true})}
  if(name.includes('stdSfxCues'))return {sfxNeedsReview:()=>false,resolveSfxCues:c=>c.map(x=>({...x,start:3}))}
  if(name.includes('stdTemplateOverlayPng'))return {persistTemplateOverlay:async(_,s)=>s,templateOverlayPng:async()=>null}
  if(name.includes('stdVideoModelStore'))return {selectedVideoModel:async()=>{calls.models++;return {config:{id:'model',provider:'fal'},fingerprint:'modelhash',secret:'never-copy-this'}}}
  throw Error(name)
 })
 const assets=[audio,image]
 return {calls,project,audio,image,assets,run:()=>exports.registerMotionAutomation(project,[{scene_number:1,scene_text:'Source scene'}],assets,'owner-id')}
}
test('AE-only submission freezes voice and original without reading a provider key',async()=>{
 const f=fixture();await f.run();assert.equal(f.calls.voice,1);assert.equal(f.calls.models,0)
 const args=f.calls.rpc[0].args,raw=args.p_manifest.automation.snapshot_json,s=JSON.parse(raw)
 assert.equal(s.scenes[0].start,0);assert.equal(s.audio.id,'voice');assert.equal(s.scenes[0].source.id,'image');assert.equal(s.model_ref,null)
 assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),args.p_hash)
})
test('hybrid freezes selected model configuration but excludes its secret',async()=>{
 const f=fixture('hybrid');await f.run();assert.equal(f.calls.models,1)
 const args=f.calls.rpc[0].args;assert.ok(!JSON.stringify(args).includes('never-copy-this'));assert.equal(JSON.parse(args.p_manifest.automation.snapshot_json).model_ref.id,'model')
})
test('resolved sound cues and background audio survive automatic submission',async()=>{
 const f=fixture();f.project.project_payload.render_settings.sfx_cues=[{library_key:'wind.wav',word_boundary:0}]
 await f.run();assert.equal(JSON.parse(f.calls.rpc[0].args.p_manifest.automation.snapshot_json).sfx_cues[0].start,3)
})
test('existing manual video remains usable without an API; vertical webtoons retain originals',async()=>{
 const f=fixture();f.assets.push({...f.image,id:'manual-video',asset_type:'video',metadata:{gcs_path:'manual.mp4'}})
 await f.run();assert.equal(JSON.parse(f.calls.rpc.at(-1).args.p_manifest.automation.snapshot_json).scenes[0].source.id,'manual-video')
 f.project.project_payload.render_settings.comic={mode:'webtoon_video'};await f.run()
 assert.equal(JSON.parse(f.calls.rpc.at(-1).args.p_manifest.automation.snapshot_json).scenes[0].source.id,'image')
})
