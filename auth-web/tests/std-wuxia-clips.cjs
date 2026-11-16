const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path')
const load=require('./load-ts-module.cjs'),api=load(path.resolve(__dirname,'../lib/stdWuxiaClips.ts'))
const clip={contract:api.WUXIA_CLIP,asset_id:'video-one',state_asset_id:'E01_S01_STATE_01',source_state_sha256:'a'.repeat(64),sha256:'b'.repeat(64),
 gcs_bucket:'private',gcs_path:'std/projects/p/clip.mp4',width:1280,height:720,duration_seconds:4,source_in_seconds:1,play_seconds:2,start_offset_seconds:.5}
const state={asset_id:clip.state_asset_id,sha256:'a'.repeat(64),start:0,end:.5}
const project=()=>({id:'p',project_payload:{structure:{wuxia_ae_package:{scenes:[{scene_id:'E01_S01',states:[state]}]}},wuxia_state_clips:{[state.asset_id]:clip}}})
test('state video uses exact source interval at normal speed and pauses/seeks deterministically',()=>{
 const p=project();assert.equal(api.wuxiaStateClipFrame(p,state,10,10,20,24),null)
 assert.equal(api.wuxiaStateClipFrame(p,state,10.5,10,20,24).source_seconds,1)
 assert.equal(api.wuxiaStateClipFrame(p,state,11.5,10,20,24).source_seconds,2)
 assert.deepEqual(api.wuxiaStateClipFrame(p,state,11,10,20,24),api.wuxiaStateClipFrame(p,state,11,10,20,24))
 assert.equal(api.wuxiaStateClipFrame(p,state,12.5,10,20,24),null)
 assert.equal(api.wuxiaStateClipFrame(p,state,10.5,10,20,24).source_seconds,1)
})
test('changed artwork and footage longer than state window fail explicitly',()=>{
 assert.throws(()=>api.wuxiaStateClipFrame(project(),{...state,sha256:'c'.repeat(64)},11,10,20,24),/연결/)
 assert.throws(()=>api.wuxiaStateClipFrame(project(),{...state,end:.1},11,10,20,24),/구간/)
 assert.equal(api.validWuxiaClip({...clip,play_seconds:5}),false)
 assert.equal(api.validWuxiaClip({...clip,width:720,height:1280}),false)
})
test('latest attachment wins; restoring still never resurrects an older clip; original untouched',()=>{
 const original=project();const asset=(id,date,enabled=true,ready=true)=>({id,created_at:date,status:'uploaded',metadata:{kind:'wuxia_state_clip',ready,enabled,clip:{...clip,asset_id:id}}})
 const assets=[asset('old','2026-11-01'),asset('new','2026-11-02',false)]
 assert.deepEqual(api.withWuxiaStateClips(original,assets).project_payload.wuxia_state_clips,{})
 assert.equal(api.withWuxiaStateClips(original,[assets[0],asset('pending','2026-11-03',true,false)]).project_payload.wuxia_state_clips[state.asset_id].asset_id,'old')
 assert.equal(original.project_payload.wuxia_state_clips[state.asset_id].asset_id,'video-one')
 assert.deepEqual(api.withWuxiaStateClips({...original,project_payload:{...original.project_payload,structure:{}}},assets).project_payload.wuxia_state_clips,{})
})
test('freeze includes original still and frame-bound clip without silent fallback',()=>{
 const {freezeWuxiaScene}=load(path.resolve(__dirname,'../lib/stdWuxiaNative.ts'))
 const p=project();p.project_payload.structure.image_style='wuxia_webtoon'
 const s=p.project_payload.structure.wuxia_ae_package.scenes[0];s.preview_duration_seconds=10;s.graphics=[];s.states[0].media_url='/api/std/assets/gcs-file?bucket=private&path=original.png';s.states.push({asset_id:'still-two',sha256:'c'.repeat(64),start:.5,end:1,media_url:'/api/std/assets/gcs-file?bucket=private&path=second.png'})
 const frozen=freezeWuxiaScene(p,1,[],0,10,24,{metadata:{}})
 assert.equal(frozen.state_clip_contract,api.WUXIA_CLIP)
 assert.equal(frozen.states[0].sha256,'a'.repeat(64))
 assert.equal(frozen.samples.filter(s=>s.video).length,48)
 assert.equal(frozen.samples[12].video.source_seconds,1)
 assert.equal(frozen.samples[60].video,undefined)
 assert.ok(frozen.samples.filter(s=>s.video).every(s=>!s.mouths.length&&!s.ambient.length))
})
test('stale enabled footage is reported for repair and never falls back to an older attachment',()=>{
 const p=project(),asset={id:'stale',created_at:'2026-11-16',status:'uploaded',metadata:{kind:'wuxia_state_clip',ready:true,enabled:true,clip:{...clip,source_state_sha256:'c'.repeat(64)}}}
 const restored=api.withWuxiaStateClips(p,[asset])
 assert.deepEqual(restored.project_payload.wuxia_state_clips,{})
 assert.equal(restored.project_payload.wuxia_state_clip_issues.length,1)
 assert.equal(restored.project_payload.wuxia_state_clip_restore_ids[state.asset_id],'stale')
})
