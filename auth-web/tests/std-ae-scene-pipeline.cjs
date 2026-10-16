const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs')
const ts = require('../node_modules/typescript'), load = require('./load-ts-module.cjs')
const mouth = load('lib/stdAeMouth.ts'), prep = load('lib/stdAeScenePreparation.ts')
const reviews = load('lib/stdAeSceneReview.ts')
const hash = 'a'.repeat(64), renderedHash = 'b'.repeat(64)
function fixture() {
 const subtitles = [1,2,3].map((n,i) => ({text:`설명 ${n}`,scene_number:n,voice_id:'n',start:i*2,end:(i+1)*2,dialogue_kind:'narration'}))
 const project = {id:'p',updated_at:'now',project_payload:{subtitles,mouth_work_policy:{enabled:false},structure:{scenes:[]}}}
 const scenes = [1,2,3].map(n => ({scene_number:n,scene_text:`설명 ${n}`}))
 const assets = [{id:'audio',asset_type:'audio',status:'uploaded',metadata:{subtitle_timeline:structuredClone(subtitles)}},
  ...scenes.map(s => ({id:`image${s.scene_number}`,scene_number:s.scene_number,asset_type:'image',status:'uploaded',metadata:{gcs_bucket:'bucket',gcs_path:`${s.scene_number}.png`}})),
  {id:'psd',scene_number:2,asset_type:'original',file_name:'scene.psd',status:'uploaded',metadata:{kind:'ae_scene_source',gcs_bucket:'bucket',gcs_path:'scene.psd',sha256:hash}}]
 const input = prep.aeScenePreparationInput(project,scenes,assets,2,'머리카락과 빛을 움직입니다.')
 const plan = {contract:'ae_scene/v1',scene_number:2,camera:[{t:0,x:.5,y:.5,scale:1},{t:1,x:.5,y:.5,scale:1.1}],
  layers:[{id:'bg',role:'background'}],transition:{in:'cut',out:'fade',fraction:.1},output:{width:1920,height:1080}}
 const prepared = {id:'prepared',scene_number:2,asset_type:'other',status:'uploaded',created_at:'2026-10-17',metadata:{kind:'ae_scene_preparation',state:'prepared',input,fingerprint:prep.aeSceneHash(input),result:{plan,plan_sha256:prep.aeSceneHash(plan),source_asset_id:'psd',source_sha256:hash,width:1920,height:1080,review:{passed:true,critical_issues:[]},files:['source_psd','source_preview','layer'].map(role=>({role,gcs_bucket:'bucket',gcs_path:role,sha256:hash}))}}}
 Object.assign(prepared.metadata.result.review,{input_fingerprint:prepared.metadata.fingerprint,source_sha256:hash,plan_sha256:prepared.metadata.result.plan_sha256,
  reviewer:'local_codex_cli',evidence:['Actual original and layers inspected'],source_identity_preserved:true,background_complete:true,motion_supported:true,continuity_checked:true})
 for(const role of ['plan','review'])prepared.metadata.result.files.push({role,gcs_bucket:'bucket',gcs_path:role,sha256:hash})
 assets.push(prepared)
 return {project,scenes,assets,prepared}
}
function pipeline() {
 const exports={}
 new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdSubmissionPipeline.ts','utf8'),{module:1,target:9}))(exports,id=> {
  if(id==='crypto') return require('crypto')
  if(id.includes('supabaseAdmin')) return {supabaseAdmin:{}}
  return load(`lib/${id.slice(2)}.ts`)
 })
 return exports
}
test('prepared narration-only AE scene enters frozen job despite mouth selection and early scene filters',()=> {
 const f=fixture(), snapshot=mouth.aeMouthInput(f.project,f.scenes,f.assets)
 assert.equal(mouth.aeMouthApplicable(f.project,f.scenes,f.assets),true)
 assert.equal(snapshot.input.version,2)
 assert.deepEqual(snapshot.input.scenes.map(s=>s.number),[2])
 assert.equal(snapshot.input.scenes[0].ae_scene.id,'prepared')
 assert.deepEqual(snapshot.input.sequence_scenes.map(s=>s.number),[1,2,3])
 assert.equal(snapshot.input.scenes[0].start,2)
 assert.equal(snapshot.input.scenes[0].end,4)
})
test('newest incomplete preparation blocks submission; frozen manifest keeps PSD and receipt immutably',()=> {
 const f=fixture(), snapshot=pipeline().submissionSnapshot(f.project,f.scenes,f.assets,false)
 assert(snapshot.assets.some(a=>a.id==='psd'))
 assert(snapshot.assets.some(a=>a.id==='prepared'))
 assert.equal(snapshot.project.project_payload.ae_mouth.enabled,true)
 f.prepared.metadata.result.files[0].gcs_path='changed'
 assert.equal(snapshot.mouth.input.scenes[0].ae_scene.metadata.result.files[0].gcs_path,'source_psd')
 f.assets.push({...f.prepared,id:'new',created_at:'2026-10-18',metadata:{...f.prepared.metadata,state:'queued'}})
 assert.throws(()=>mouth.aeMouthInput(f.project,f.scenes,f.assets),/준비가 끝난/)
})
test('saving TTS does not start submitted AE scene production',async()=> {
 const f=fixture()
 assert.equal(await pipeline().ensureSyncedMouthPreview(f.project,f.scenes,f.assets),null)
})
test('explicit mouth and blink work cannot be silently dropped by prepared PSD production',()=> {
 const f=fixture()
 Object.assign(f.project.project_payload.subtitles[1],{dialogue_kind:'dialogue',dialogue_speaker:'주인공'})
 f.assets.push({id:'mouth-selection',asset_type:'other',status:'uploaded',metadata:{kind:'mouth_work_selection',scene_numbers:[2]}})
 assert.throws(()=>mouth.aeMouthInput(f.project,f.scenes,f.assets),/입모양 후작업이 함께 선택/)
 f.project.project_payload.ae_mouth={enabled:false}
 assert.deepEqual(pipeline().submissionSnapshot(f.project,f.scenes,f.assets,false).mouth.input.scenes.map(s=>s.number),[2])
 f.assets.push({id:'manual-blink',scene_number:2,asset_type:'other',status:'uploaded',metadata:{kind:'eye_blink_confirmation',state:'confirmed',image_id:'image2'}})
 assert.throws(()=>mouth.aeMouthInput(f.project,f.scenes,f.assets),/수동 눈깜빡임/)
})
function completed() {
 const f=fixture(), input=mouth.aeMouthInput(f.project,f.scenes,f.assets)
 const check=ids=>({passed:true,critical_issues:[],checks:ids.map(id=>({id,passed:true,evidence:'Observed actual labeled source and output pixels'}))})
 const seconds=reviews.aeSceneReviewSampleTimes(f.prepared.metadata.result.plan,2)
 const review={passed:true,version:1,method:'sampled_actual_frames_and_decoded_final_audio',render_sha256:renderedHash,
  source_sha256:hash,source_preview_sha256:hash,plan_sha256:f.prepared.metadata.result.plan_sha256,
  audio:{source_audio_id:'audio',final_audio_sha256:hash,method:'decoded_pcm_integrity_not_audio_audition',sample_rate:8000,
   scene_start_seconds:2,scene_end_seconds:4,correlation:1,rms_ratio:1,source_samples:16000,output_samples:16000},
  video:{fps:24,frames:48,duration:2,width:1920,height:1080},
  batches:[{seconds,frames:seconds.map(seconds=>({seconds,sha256:hash})),review:check(reviews.AE_RENDER_CHECKS)}]}
 const result={number:2,status:'artifact_ready',asset_id:'output',render_sha256:renderedHash,output_review:review}
 const job={metadata:{state:'artifact_ready',...input,results:[result]}}
 const metadata={kind:'ae_scene_output',artifact_ready:true,timing_locked:true,voice_synced:true,duration_seconds:2,source_audio_id:'audio',render_sha256:renderedHash,ae_mouth_fingerprint:input.fingerprint,ae_reviewed:true,ae_scene_review:review,ae_scene_preparation_id:'prepared',ae_scene_preparation_fingerprint:f.prepared.metadata.fingerprint,plan_sha256:f.prepared.metadata.result.plan_sha256,source_psd_id:'psd',source_sha256:hash}
 const output={id:'output',scene_number:2,asset_type:'video',status:'uploaded',metadata}
 const evidence=scene=>({number:scene.number,kind:scene.ae_scene?'actual_postprocessed_output':'original_image',
  media_sha256:scene.ae_scene?renderedHash:hash,source_asset_id:scene.selected_media?.id,
  source_storage:scene.selected_media?.metadata,frames:[{seconds:0,sha256:hash}]})
 job.metadata.sequence_review={passed:true,version:1,method:'sampled_actual_adjacent_frames',ae_scene_numbers:[2],
  checked_boundaries:input.input.sequence_scenes.slice(1).map((right,i)=>({from:input.input.sequence_scenes[i].number,to:right.number,
   evidence:[evidence(input.input.sequence_scenes[i]),evidence(right)],review:check(reviews.AE_BOUNDARY_CHECKS)})),
  fingerprint:mouth.aeSceneSequenceFingerprint(job)}
 return {job,output,f}
}
test('required AE output requires matching plan, real output review and current sequence review',()=> {
 const {job,output}=completed()
 assert.equal(mouth.readyPipelineMouthAssets(job,[output]).get(2).id,'output')
 for(const change of [{ae_scene_review:{passed:false}},{plan_sha256:'wrong'},{source_psd_id:'other'},{ae_reviewed:false}]) {
  assert.throws(()=>mouth.readyPipelineMouthAssets(job,[{...output,metadata:{...output.metadata,...change}}]),/검수/)
 }
 job.metadata.results[0]={number:2,status:'skipped',fallback:'original'}
 assert.throws(()=>mouth.readyPipelineMouthAssets(job,[output]),/완료되지/)
 const fresh=completed();fresh.job.metadata.sequence_review.fingerprint='stale'
 assert.throws(()=>mouth.readyPipelineMouthAssets(fresh.job,[fresh.output]),/연결 검수/)
})
test('submitted frozen job survives later preparation disable without selecting new sources',()=> {
 const f=fixture(), frozen={id:'job',asset_type:'other',status:'uploaded',metadata:{kind:'ae_mouth_job',pipeline_run_id:'run'}}
 f.prepared.metadata.enabled=false;f.project.submitted_at='now';f.project.progress_payload={pipeline_run_id:'run'}
 assert.equal(mouth.currentAeMouthJob(f.project,f.scenes,[...f.assets,frozen]).id,'job')
})
test('disabled mouth settings cannot bypass a required AE scene or reuse a legacy skipped result',()=> {
 const f=fixture();f.project.project_payload.ae_mouth={enabled:false}
 assert.throws(()=>mouth.reviewedAeMouthAssets(f.project,f.scenes,f.assets),/제출 단계/)
 const frozen=mouth.aeMouthInput(f.project,f.scenes,f.assets)
 f.assets.push({id:'legacy-job',asset_type:'other',status:'uploaded',metadata:{kind:'ae_mouth_job',state:'reviewed',...frozen,results:[{number:2,status:'skipped'}]}})
 assert.throws(()=>mouth.reviewedAeMouthAssets(f.project,f.scenes,f.assets),/제출 단계/)
 f.assets=f.assets.filter(a=>a.metadata?.kind!=='ae_scene_preparation')
 assert.equal(mouth.reviewedAeMouthAssets(f.project,f.scenes,f.assets).size,0)
})
test('unordered scene query produces sorted frozen boundaries',()=> {
 const f=fixture(), a=mouth.aeMouthInput(f.project,f.scenes,f.assets), b=mouth.aeMouthInput(f.project,[f.scenes[2],f.scenes[0],f.scenes[1]],f.assets)
 assert.equal(a.fingerprint,b.fingerprint)
 assert.deepEqual(b.input.sequence_scenes.map(s=>[s.number,s.start,s.end]),[[1,0,2],[2,2,4],[3,4,6]])
})
test('required output rejects stale audio, missing checks, and incomplete actual frame coverage',()=> {
 const changes=[r=>{r.audio.source_audio_id='old'},r=>{r.audio.correlation=.5},r=>{r.audio.output_samples=100},
  r=>{r.source_preview_sha256='c'.repeat(64)},r=>{r.batches[0].review.checks.pop()},r=>{r.batches[0].review.checks[0].evidence=' '},
  r=>{r.batches[0].seconds.pop();r.batches[0].frames.pop()},r=>{r.batches[0].frames[0].sha256='missing'},r=>{r.video.frames=24}]
 for(const change of changes){const {job,output}=completed();change(output.metadata.ae_scene_review);assert.throws(()=>mouth.readyPipelineMouthAssets(job,[output]),/출력 검수/)}
 const {job,output}=completed();job.metadata.results[0].output_review={passed:true,render_sha256:renderedHash}
 assert.throws(()=>mouth.readyPipelineMouthAssets(job,[output]),/출력 검수/)
})
test('submission reuses a required output only after validating both saved review receipts',()=> {
 const {job,output,f}=completed()
 Object.assign(job,{id:'saved-job',asset_type:'other',status:'uploaded'})
 Object.assign(job.metadata,{kind:'ae_mouth_job',pipeline_version:2})
 const assets=[...f.assets,job,output]
 assert.equal(pipeline().submissionSnapshot(f.project,f.scenes,assets,true).reusable_results.length,1)
 job.metadata.results[0].output_review={passed:true,render_sha256:renderedHash}
 assert.equal(pipeline().submissionSnapshot(f.project,f.scenes,assets,true).reusable_results.length,0)
})
test('sequence review requires complete boundaries and the frozen adjacent media',()=> {
 const changes=[r=>{r.checked_boundaries.pop()},r=>{r.checked_boundaries[0].evidence[0].source_asset_id='other'},
  r=>{r.checked_boundaries[0].evidence[0].source_storage={gcs_path:'other.png'}},r=>{r.checked_boundaries[0].evidence[1].media_sha256=hash},
  r=>{r.checked_boundaries[1].review.checks[0].passed=false},r=>{r.checked_boundaries[0].evidence[0].frames=[]}]
 for(const change of changes){const {job,output}=completed();change(job.metadata.sequence_review);assert.throws(()=>mouth.readyPipelineMouthAssets(job,[output]),/연결 검수/)}
 const {job}=completed(), sequence=job.metadata.input.sequence_scenes
 const empty={number:2.5,start:4,end:4,ae_scene:null}
 assert.equal(reviews.aeSceneSequenceReviewMatches([...sequence,empty],job.metadata.results,job.metadata.sequence_review),true)
 assert.equal(reviews.aeSceneSequenceReviewMatches([...sequence,{...empty,ae_scene:sequence[1].ae_scene}],job.metadata.results,job.metadata.sequence_review),false)
})

function submitFixture(options={}) {
 const f=fixture(), calls=[]
 Object.assign(f.project,{employee_email:'owner@test',status:'in_progress',progress_payload:{}})
 f.project.project_payload.ae_mouth={enabled:false}
 f.assets.find(a=>a.id==='audio').metadata.gcs_path='audio.wav'
 f.assets.push({id:'thumb',asset_type:'thumbnail',metadata:{gcs_path:'thumb.png'},status:'uploaded'})
 f.assets=f.assets.filter(a=>a.id!=='image2' && (!options.missingNeighbor || a.id!=='image1'))
 const refreshed=prep.aeScenePreparationInput(f.project,f.scenes,f.assets,2,'머리카락과 빛을 움직입니다.')
 f.prepared.metadata.input=refreshed;f.prepared.metadata.fingerprint=prep.aeSceneHash(refreshed)
 f.prepared.metadata.result.review.input_fingerprint=f.prepared.metadata.fingerprint
 if(options.pending)f.prepared.metadata.state='queued'
 const db={from(table){const q={select:()=>q,eq:()=>q,order:()=>q,maybeSingle:async()=>({data:f.project}),
  then(resolve){resolve({data:table==='std_project_scenes'?[f.scenes[2],f.scenes[0],f.scenes[1]]:[]})}};return q}}
 const exports={}
 new Function('exports','require',ts.transpile(fs.readFileSync('app/api/std/projects/[projectId]/submit/route.ts','utf8'),{module:1,target:9}))(exports,id=>{
  if(id==='next/server')return {NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}}
  if(id.includes('supabaseAdmin'))return {supabaseAdmin:db}
  if(id.includes('stdWeb'))return {requireStdUser:async()=>({ok:true,requester:{email:'owner@test',user:{id:'u'}}})}
  if(id.includes('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:f.assets})}
  if(id.includes('stdRenderQueue'))return {ensureStdGeneratedSceneAssetsArchived:async(p,s,a)=>a}
  if(id.includes('stdThumbnailRender'))return {editableThumbnailError:()=>null}
  if(id.includes('stdPolicy'))return {isStdVideoPromptScene:n=>n===2}
  if(id.includes('stdLegacySync'))return {}
  if(id.includes('stdSubmissionPipeline'))return {registerSubmissionPipeline:async(p,s,a,u,required)=>{
   calls.push({required,scenes:s.map(s=>s.scene_number),snapshot:pipeline().submissionSnapshot(p,s,a,required)});return {id:'run'}}}
  return load(`lib/${id.split('/').pop()}.ts`)
 })
 return {calls,run:()=>exports.POST({}, {params:{projectId:'p'}})}
}
test('submit accepts a verified prepared PSD without MP4 and freezes sorted scene order',async()=> {
 const f=submitFixture(), response=await f.run()
 assert.equal(response.status,202,JSON.stringify(response.body))
 assert.equal(f.calls[0].required,true)
 assert.deepEqual(f.calls[0].scenes,[1,2,3])
 assert.equal(f.calls[0].snapshot.mouth.input.scenes[0].ae_scene.id,'prepared')
})
test('submit exempts only fully prepared AE scenes and keeps missing ordinary media blocked',async()=> {
 const missing=submitFixture({missingNeighbor:true}), response=await missing.run()
 assert.equal(response.status,409);assert.deepEqual(response.body.missing_scene_numbers,[1]);assert.equal(missing.calls.length,0)
 const pending=submitFixture({pending:true}), blocked=await pending.run()
 assert.equal(blocked.status,409);assert.match(blocked.body.error,/준비가 끝난/);assert.equal(pending.calls.length,0)
})
