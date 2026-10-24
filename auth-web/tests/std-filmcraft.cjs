const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),crypto=require('node:crypto')
const load=require('./load-ts-module.cjs'),motion=load('lib/stdMotionStudio.ts')
const pin=JSON.parse(fs.readFileSync('lib/filmcraftSource.json','utf8'))
function fixture(method='filmcraft'){
 const calls=[],project={id:'p',updated_at:'now',employee_email:'owner@test',project_payload:{subtitles:[{text:'recorded',scene_number:1}],render_settings:{motion:motion.switchMotionProduction({version:1,enabled:false,aspect:'16:9',fps:30,scenes:{}},method)}}}
 const audio={id:'voice',asset_type:'audio',status:'uploaded',metadata:{gcs_path:'voice.wav',subtitle_timeline:[{start:0,end:2}]}},image={id:'image',scene_number:1,asset_type:'image',created_at:'now',status:'uploaded',metadata:{gcs_path:'image.png'}}
 const assets=[audio,image],exports={}
 new Function('exports','require',ts.transpileModule(fs.readFileSync('lib/stdMotionAutomation.ts','utf8'),{compilerOptions:{module:1,target:9,esModuleInterop:true}}).outputText)(exports,name=>{
  if(name.includes('stdMotionSourceReuse'))return {recordedMotionSourceReuse:()=>null}
  if(name.includes('stdVideoPlaybackPolicy'))return require('./load-ts-module.cjs')('lib/stdVideoPlaybackPolicy.ts')
  if(name.includes('stdHorizontalWebtoon'))return {horizontalWebtoon:()=>false,webtoonInputs:()=>[],readyWebtoonPlan:()=>null}
  if(name==='crypto')return crypto
  if(name.endsWith('.json'))return JSON.parse(fs.readFileSync('lib/'+name.slice(2),'utf8'))
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:{rpc:async(name,args)=>{calls.push({name,args});return {data:{job_id:'queued'}}}}}
  if(name.includes('stdMotionStudio'))return motion
  if(name.includes('stdWorkflowBoundary'))return {assertPreparationFinished:()=>{}}
  if(name.includes('stdSceneExecution'))return {directedScene:()=>false,bindSceneDirection:()=>null}
  if(name.includes('stdAeScenePreparation'))return {aeSceneSources:()=>new Map([[1,assets.find(a=>a.asset_type==='original')]]),preparedAeScenes:()=>new Map()}
  if(name.includes('stdContentIdentity'))return {selectNarrationAsset:()=>audio}
  if(name.includes('stdLipSync'))return {lipSyncPlan:()=>{},lipSyncSceneStarts:()=>[0],reviewedLipSyncAssets:()=>new Map()}
  if(name.includes('stdSceneMedia'))return {storageSourceForAsset:a=>a?.metadata?.gcs_path}
  if(name.includes('stdAudioMix'))return {backgroundWindow:()=>({valid:true})}
  if(name.includes('stdSfxCues'))return {sfxNeedsReview:()=>false,resolveSfxCues:c=>c}
  if(name.includes('stdTemplateOverlayPng'))return {persistTemplateOverlay:async(_,s)=>s,templateOverlayPng:async()=>null}
  if(name.includes('stdVideoModelStore'))return {selectedVideoModel:async()=>{throw Error('No video API in non-hybrid mode')}}
  throw Error(name)
 })
 return {project,assets,calls,run:()=>exports.registerMotionAutomation(project,[{scene_number:1,scene_text:'recorded'}],assets,'owner')}
}
test('FilmCraft settings roundtrip while preserving each existing renderer draft',()=>{
 const original={version:1,enabled:false,aspect:'9:16',fps:24,scenes:{}}
 let draft=motion.switchMotionProduction(original,'effectcraft');const effect=structuredClone(draft)
 draft=motion.switchMotionProduction(draft,'filmcraft')
 assert.equal(draft.automation.mode,'ae_only');assert.equal(motion.motionProductionMethod({project_payload:{render_settings:{motion:draft}}}),'filmcraft')
 assert.deepEqual(motion.switchMotionProduction(draft,'effectcraft').scenes,effect.scenes)
 assert.deepEqual(motion.switchMotionProduction(draft,'ae').scenes,original.scenes)
 assert.equal(motion.normalizeMotionDraft(draft).production_method,'filmcraft')
})
test('FilmCraft queue freezes exact native revision, voice and source in separate RPC',async()=>{
 const f=fixture();await f.run();const call=f.calls[0],snapshot=JSON.parse(call.args.p_manifest.automation.snapshot_json)
 assert.equal(call.name,'register_std_filmcraft_pipeline');assert.equal(snapshot.renderer.engine,'filmcraft');assert.equal(snapshot.renderer.revision,pin.revision);assert.equal(snapshot.renderer.adapter,'filmcraft-native-timeline-gpu-v3-balanced');assert.equal(snapshot.renderer.profile,'legacy-matched-1080p24-v1');assert.equal(snapshot.renderer.gpu_composition,'required')
 assert.equal(snapshot.audio.id,'voice');assert.equal(snapshot.scenes[0].source.id,'image');assert.equal(snapshot.scenes[0].end,2)
 assert.equal(crypto.createHash('sha256').update(call.args.p_manifest.automation.snapshot_json).digest('hex'),call.args.p_hash)
})
test('FilmCraft chooses a usable image ahead of raw PSD; explicit PSD fails before queuing',async()=>{
 const f=fixture();f.assets.push({...f.assets[1],id:'psd',asset_type:'original'})
 await f.run();assert.equal(JSON.parse(f.calls[0].args.p_manifest.automation.snapshot_json).scenes[0].source.id,'image')
 f.project.project_payload.render_settings.motion.scenes['1']={...motion.motionScene(),source:'psd'}
 await assert.rejects(f.run(),/PSD/);assert.equal(f.calls.length,1)
})
test('Existing EffectCraft still uses its original isolated RPC',async()=>{
 const f=fixture('effectcraft');await f.run();assert.equal(f.calls[0].name,'register_std_effectcraft_pipeline')
})
test('AE and EffectCraft effect engines remain independent of the FilmCraft final renderer',async()=>{
 for(const method of ['ae','effectcraft'])for(const finalRenderer of ['python','filmcraft']){
  const f=fixture(method);const raw=f.project.project_payload.render_settings.motion;raw.enabled=true;raw.final_renderer=finalRenderer;raw.automation={mode:'ae_only',max_ai_clips:1,max_ai_seconds:5};await f.run()
  const snapshot=JSON.parse(f.calls[0].args.p_manifest.automation.snapshot_json)
  assert.equal(f.calls[0].name,method==='ae'?'register_std_motion_pipeline':'register_std_effectcraft_pipeline');assert.equal(snapshot.motion.production_method,method);assert.equal(snapshot.final_renderer?.engine,finalRenderer==='filmcraft'?'filmcraft':undefined)
 }
})
