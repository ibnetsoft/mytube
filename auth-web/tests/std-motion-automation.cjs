const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),crypto=require('crypto')
function fixture(mode='ae_only', alternativesEnabled=false) {
 const calls={models:0,voice:0,rpc:[],psds:new Map(),prepared:new Map()},exports={}
 const project={id:'qa-project',updated_at:'now',employee_email:'owner@test',project_payload:{render_settings:{motion:{version:1,enabled:true,aspect:'9:16',fps:24,scenes:{},automation:{mode,max_ai_clips:1,max_ai_seconds:5}}},subtitles:[{text:'Final voice',scene_number:1,start:0,end:20}]}}
 const audio={id:'voice',asset_type:'audio',status:'uploaded',metadata:{gcs_path:'voice.wav',subtitle_timeline:[{start:0,end:20}]}},image={id:'image',asset_type:'image',scene_number:1,status:'uploaded',created_at:'now',metadata:{gcs_path:'source.png'}}
 new Function('exports','require',ts.transpileModule(fs.readFileSync('lib/stdMotionAutomation.ts','utf8'),{compilerOptions:{module:1,target:9,esModuleInterop:true}}).outputText)(exports,name=>{
 if(name.includes('stdProductionEnginePolicy'))return alternativesEnabled?{productionEngineError:()=>null}:require('./load-ts-module.cjs')('lib/stdProductionEnginePolicy.ts');
  if(name.includes('stdSubmittedVideoPostwork'))return require('./load-ts-module.cjs')('lib/stdSubmittedVideoPostwork.ts')
  if(name==='crypto')return crypto
  if(name.includes('stdMotionSourceReuse'))return {recordedMotionSourceReuse:()=>null}
  if(name.endsWith('.json'))return JSON.parse(fs.readFileSync('lib/'+name.slice(2),'utf8'))
  if(name.includes('stdWorkflowBoundary'))return {assertPreparationFinished:()=>{}}
  if(name.includes('stdSceneExecution'))return {directedScene:()=>false,bindSceneDirection:()=>null}
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:{rpc:async(name,args)=>{calls.rpc.push({name,args});return {data:{job_id:'queued'},error:null}}}}
  if(name.includes('stdMotionStudio'))return {...require('./load-ts-module.cjs')('lib/stdMotionStudio.ts'),motionForProject:p=>p.project_payload.render_settings.motion}
  if(name.includes('stdHorizontalWebtoon'))return {horizontalWebtoon:p=>p.project_payload.render_settings.motion.edit_mode==='horizontal_webtoon',webtoonInputs:()=>[{number:1,asset:image,start:0,end:20}],readyWebtoonPlan:()=>({source_sha256:'a'.repeat(64),plan:{version:1,shots:[{start:0,end:1,panels:[]}],evidence:['fixture']}})}
  if(name.includes('stdAeScenePreparation'))return {aeSceneSources:()=>calls.psds,preparedAeScenes:()=>calls.prepared}
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
test('horizontal webtoon freezes the inspected plan and uses a queue older workers cannot claim',async()=>{
 const f=fixture();f.project.project_payload.render_settings.motion.edit_mode='horizontal_webtoon'
 f.project.project_payload.render_settings.motion.aspect='16:9'
 await f.run();const call=f.calls.rpc[0],s=JSON.parse(call.args.p_manifest.automation.snapshot_json)
 assert.equal(call.name,'register_std_horizontal_webtoon_pipeline');assert.deepEqual(s.renderer,{engine:'ae_horizontal_webtoon',version:1})
 assert.equal(s.scenes[0].source.id,'image');assert.equal(s.scenes[0].webtoon.source_sha256,'a'.repeat(64));assert.equal(f.calls.models,0)
 assert.equal(s.execution_policy.review_policy,'skip_user_requested/v1');assert.equal(s.execution_policy.video_playback_policy,'original_speed_no_freeze_no_loop/v1')
})
test('hybrid freezes selected model configuration but excludes its secret',async()=>{
 const f=fixture('hybrid');await f.run();assert.equal(f.calls.models,1)
 const args=f.calls.rpc[0].args;assert.ok(!JSON.stringify(args).includes('never-copy-this'));assert.equal(JSON.parse(args.p_manifest.automation.snapshot_json).model_ref.id,'model')
})

test('EffectCraft freezes bounded post-submission supplementation while final voice and subtitle times remain exact',async()=>{
 const f=fixture('ae_only',true);f.project.project_payload.render_settings.motion.production_method='effectcraft'
 await f.run()
 const args=f.calls.rpc[0].args,s=JSON.parse(args.p_manifest.automation.snapshot_json)
 assert.equal(f.calls.rpc[0].name,'register_std_effectcraft_pipeline')
 assert.deepEqual(s.supplemental_assets,{contract:'ec_supplemental/v1',enabled:true,max_layers_per_scene:4,max_attempts:2})
 assert.equal(s.audio.id,f.audio.id);assert.equal(s.scenes[0].source.id,f.image.id)
 assert.deepEqual(s.subtitles.map(r=>[r.start,r.end]),[[0,20]])
 assert.equal(f.calls.models,0)
})
test('resolved sound cues and background audio survive automatic submission',async()=>{
 const f=fixture();f.project.project_payload.render_settings.sfx_cues=[{library_key:'wind.wav',word_boundary:0}]
 await f.run();assert.equal(JSON.parse(f.calls.rpc[0].args.p_manifest.automation.snapshot_json).sfx_cues[0].start,3)
})
test('uploaded scenes 1..18 retain their actual video even when a legacy still default exists',async()=>{
 const f=fixture();f.assets.push({...f.image,id:'manual-video',asset_type:'video',metadata:{gcs_path:'manual.mp4'}})
 await f.run();assert.equal(JSON.parse(f.calls.rpc.at(-1).args.p_manifest.automation.snapshot_json).scenes[0].source.id,'manual-video')
 f.project.project_payload.render_settings.comic={mode:'webtoon_video'};await f.run()
 assert.equal(JSON.parse(f.calls.rpc.at(-1).args.p_manifest.automation.snapshot_json).scenes[0].source.id,'manual-video')
})

test('EffectCraft freezes bounded post-submission supplementation while final voice and subtitle times remain exact',async()=>{
 const f=fixture('ae_only',true);f.project.project_payload.render_settings.motion.production_method='effectcraft'
 await f.run()
 const args=f.calls.rpc[0].args,s=JSON.parse(args.p_manifest.automation.snapshot_json)
 assert.equal(f.calls.rpc[0].name,'register_std_effectcraft_pipeline')
 assert.deepEqual(s.supplemental_assets,{contract:'ec_supplemental/v1',enabled:true,max_layers_per_scene:4,max_attempts:2})
 assert.equal(s.audio.id,f.audio.id);assert.equal(s.scenes[0].source.id,f.image.id)
 assert.deepEqual(s.subtitles.map(r=>[r.start,r.end]),[[0,20]])
 assert.equal(f.calls.models,0)
})

test('EC defaults to existing stored video despite stale image choice and freezes no-review policy',async()=>{
 const f=fixture('hybrid',true);f.project.project_payload.render_settings.motion.production_method='effectcraft';f.project.project_payload.render_settings.motion.scenes['1']={source:'image'};
 f.assets.push({...f.image,id:'stored-video',asset_type:'video',metadata:{gcs_path:'stored.mp4'}});
 await f.run();const s=JSON.parse(f.calls.rpc[0].args.p_manifest.automation.snapshot_json);
 assert.equal(s.scenes[0].source.id,'stored-video');assert.equal(s.scenes[0].source_kind,'video');assert.equal(s.scenes[0].source_reference_image.id,'image');
 assert.equal(s.execution_policy.review_policy,'skip_user_requested/v1');assert.equal(s.motion.automation.mode,'ae_only');assert.equal(f.calls.models,0);assert.equal(s.model_ref,null);
 assert.deepEqual(s.subtitles.map(x=>[x.start,x.end]),[[0,20]]);
});
test('EC falls back to stored image when video has no storage',async()=>{
 const f=fixture('ae_only',true);f.project.project_payload.render_settings.motion.production_method='effectcraft';f.assets.push({...f.image,id:'missing-video',asset_type:'video',metadata:{}});
 await f.run();const s=JSON.parse(f.calls.rpc[0].args.p_manifest.automation.snapshot_json);assert.equal(s.scenes[0].source_kind,'image');
});

test('frozen derivatives are excluded in favor of original stored video',async()=>{
 const f=fixture('ae_only',true);f.project.project_payload.render_settings.motion.production_method='effectcraft';
 f.assets.push({...f.image,id:'original-video',asset_type:'video',metadata:{gcs_path:'original.mp4'}});
 f.assets.unshift({...f.image,id:'frozen-video',asset_type:'video',created_at:'zz',metadata:{gcs_path:'frozen.mp4',kind:'repaired_source_clip'}});
 await f.run();const s=JSON.parse(f.calls.rpc[0].args.p_manifest.automation.snapshot_json);
 assert.equal(s.scenes[0].source.id,'original-video');assert.equal(s.execution_policy.video_playback_policy,'original_speed_no_freeze_no_loop/v1');
});
test('only frozen video is reported instead of silently substituting image',async()=>{
 const f=fixture('ae_only',true);f.project.project_payload.render_settings.motion.production_method='effectcraft';f.assets.push({...f.image,id:'frozen-video',asset_type:'video',metadata:{gcs_path:'frozen.mp4',tail_policy:'hold_last_frame'}});
 await assert.rejects(f.run(),/원본 영상/);assert.equal(f.calls.rpc.length,0);
});

test('disabled alternatives cannot register a queue or read provider secrets',async()=>{for(const method of ['effectcraft','filmcraft','motion_studio']){const f=fixture();f.project.project_payload.render_settings.motion.production_method=method;await assert.rejects(f.run(),/비활성화/);assert.equal(f.calls.rpc.length,0);assert.equal(f.calls.models,0)}});

test('ordinary uploaded dialogue videos enter mandatory reviewed postwork even with automation disabled',async()=>{const f=fixture();f.project.project_payload.render_settings.motion.enabled=false;delete f.project.project_payload.render_settings.motion.automation;f.project.project_payload.subtitles[0].dialogue_kind='dialogue';f.project.project_payload.subtitles[0].dialogue_speaker='주인공';f.assets.push({...f.image,id:'submitted-clip',asset_type:'video',metadata:{gcs_path:'clip.mp4',video_tail_policy:'original_speed_no_freeze_no_loop/v1'}});await f.run();const s=JSON.parse(f.calls.rpc[0].args.p_manifest.automation.snapshot_json);assert.equal(s.submitted_video_postwork,'submitted_video_postwork/v1');assert.equal(s.scenes[0].source.id,'submitted-clip');assert.equal(s.scenes[0].postwork.mouth_required,true);assert.equal(s.scenes[0].postwork.dialogue[0].end,20);assert.equal(s.motion.automation.mode,'ae_only');assert.equal(s.execution_policy.review_policy,'required_actual_source_output/v1');assert.equal(f.calls.models,0);});

test('script-selected parallax never silently submits a flattened image',async()=>{const f=fixture();f.project.project_payload.structure={scenes:[{scene_number:1,parallax_plan:{enabled:true}}]};await assert.rejects(f.run(),/패럴럭스.*PSD/);assert.equal(f.calls.rpc.length,0);});

test('all-scene parallax automatically registers prepared PSD with exact dialogue clock and no uploaded video',async()=>{
 const f=fixture();f.project.project_payload.render_settings.motion.enabled=false;
 f.project.project_payload.structure={parallax_mode:'all_scenes',scenes:[{scene_number:1,parallax_plan:{enabled:true}}]};
 f.project.project_payload.subtitles[0].dialogue_kind='dialogue';f.project.project_payload.subtitles[0].dialogue_speaker='hero';
 f.calls.psds.set(1,{id:'psd',scene_number:1,asset_type:'original',status:'uploaded',metadata:{gcs_path:'layers.psd'}});
 const approvedDepth={type:'depth_background_blur',target_layer:'background',blur_pixels:6,start:0,end:1,intensity:.2,reason:'Reviewed distant garden'};
 f.calls.prepared.set(1,{metadata:{state:'prepared',result:{plan:{effects:[approvedDepth],camera:[{t:0,x:.5,y:.5,scale:1,rotation:0},{t:1,x:.5,y:.5,scale:1,rotation:0}]}}}});
 await f.run();const s=JSON.parse(f.calls.rpc[0].args.p_manifest.automation.snapshot_json);
 assert.deepEqual(s.scenes[0].reviewed_depth_effects,[approvedDepth]);
 assert.equal(s.all_scene_parallax,'all_scene_parallax/v1');assert.equal(s.scenes[0].source_kind,'psd');assert.equal(s.scenes[0].parallax_mouth.dialogue[0].start,0);assert.equal(s.scenes[0].parallax_mouth.dialogue[0].end,20);assert.equal(s.scenes[0].parallax_mouth.dialogue[0].speaker,'hero');assert.equal(s.execution_policy.review_policy,'required_actual_source_output/v1');assert.equal(f.calls.models,0);
});
