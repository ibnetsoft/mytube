const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), ts = require('../node_modules/typescript')
const load = require('./load-ts-module.cjs')
const mouth = load('lib/stdAeMouth.ts')
function snapshot() {
 const ex = {}, source = fs.readFileSync('lib/stdSubmissionPipeline.ts', 'utf8')
 new Function('exports','require',ts.transpile(source,{module:1,target:9}))(ex,id => {
  if (id === 'crypto') return require('crypto')
  if (id.includes('supabaseAdmin')) return {supabaseAdmin:{}}
  if (id.includes('stdAeMouth')) return {aeMouthInput:()=>({input:{scenes:[]},fingerprint:'f'}),currentAeMouthJob:()=>null}
  if (id.includes('stdAeScenePreparation')) return load('lib/stdAeScenePreparation.ts')
  if (id.includes('stdAeSceneReview')) return load('lib/stdAeSceneReview.ts')
  if (id.includes('stdAudioMix')) return load('lib/stdAudioMix.ts')
  if (id.includes('stdWorkflowBoundary')) return load('lib/stdWorkflowBoundary.ts')
  if (id.includes('stdSfxCues')) return load('lib/stdSfxCues.ts')
  throw new Error(id)
 })
 return ex.submissionSnapshot
}
test('freeze preserves exact web BGM/SFX settings including false, zero and disabled cues',()=> {
 const p={id:'p',project_payload:{subtitles:[{id:'s',text:'line',scene_number:100,start:10,end:15}],
  render_settings:{bgm_asset_id:'bgm',bgm_start_scene:100,bgm_start_subtitle:1,bgm_loop:false,bgm_volume:0,sfx_cues:[{enabled:false,asset_id:'missing'},{enabled:true,asset_id:'sfx',subtitle_id:'s',word_boundary:0,volume_db:8}]}}}
 const frozen=snapshot()(p,[],[{id:'bgm'},{id:'sfx'}],false)
 assert.deepEqual(frozen.project.project_payload.render_settings,p.project_payload.render_settings)
 p.project_payload.render_settings.bgm_loop=true;p.project_payload.subtitles.push({text:'draft'})
 assert.equal(frozen.project.project_payload.render_settings.bgm_loop,false)
 assert.equal(frozen.project.project_payload.subtitles.length,1)
})
test('invalid music anchor or missing selected effect fails before submission',()=>{
 const p={project_payload:{subtitles:[],render_settings:{bgm_asset_id:'b',bgm_start_scene:100}}}
 assert.throws(()=>snapshot()(p,[],[{id:'b'}],false),/배경음/)
 p.project_payload.render_settings={sfx_cues:[{enabled:true,asset_id:'missing'}]}
 assert.throws(()=>snapshot()(p,[],[],false),/효과음/)
})
test('technical ready output ignores historical aesthetic review but binds audio, hash and duration',()=>{
 const job={metadata:{state:'artifact_ready',fingerprint:'f',input:{audio:{id:'a'},scenes:[{number:23,start:0,end:3},{number:24,start:3,end:4}]},
 results:[{number:23,status:'artifact_ready',asset_id:'v',render_sha256:'h'},{number:24,status:'skipped',skip_reason:'composition_failed',fallback:'original'}]}}
 const asset={id:'v',status:'uploaded',asset_type:'video',scene_number:23,metadata:{artifact_ready:true,ae_reviewed:false,source_audio_id:'a',render_sha256:'h',ae_mouth_fingerprint:'f',timing_locked:true,duration_seconds:3}}
 assert.equal(mouth.readyPipelineMouthAssets(job,[asset]).get(23).id,'v')
 assert.throws(()=>mouth.readyPipelineMouthAssets(job,[{...asset,metadata:{...asset.metadata,source_audio_id:'wrong'}}]),/일치/)
 for(const preview of [{kind:'mouth_preview'},{timing_mode:'preview_cycle'},{voice_synced:false}]) {
  assert.throws(()=>mouth.readyPipelineMouthAssets(job,[{...asset,metadata:{...asset.metadata,...preview}}]),/일치/)
 }
})
