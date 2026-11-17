const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs')
const {withWuxiaAnatomyHolds}=load('lib/stdWuxiaArtQuality.ts'),{freezeWuxiaScene}=load('lib/stdWuxiaNative.ts'),sha='a'.repeat(64)
const policy={anatomy_auto:{contract:'wuxia_anatomy_review/v1',enabled:true},energy_auto:{enabled:true,auto_prepare:true}}
const state={asset_id:'art',sha256:sha,start:0,end:1,face_exclusion_boxes:[],ambient_loops:[],dialogue_mouths:[],media_url:'/api/std/assets/gcs-file?bucket=test&path=art.png'}
const pkg=()=>({contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'E01_S01',preview_duration_seconds:2,states:[{...state}],graphics:[],effects:[]}],mouth_preparation:{anatomy_reviews:[{contract:'wuxia_anatomy_review/v1',asset_id:'art',source_sha256:sha,passed:false,decision:'uncertain',repair_request:{status:'reviewed_repair_request'}}]}})
test('only opted-in source-bound findings hold animation; original package is immutable',()=>{
 const p=pkg(),before=JSON.stringify(p);assert.equal(withWuxiaAnatomyHolds(p,{}),p)
 assert.equal(withWuxiaAnatomyHolds(p,policy).scenes[0].states[0].anatomy_hold.decision,'uncertain')
 p.mouth_preparation.anatomy_reviews[0].source_sha256='b'.repeat(64);assert.equal(withWuxiaAnatomyHolds(p,policy).scenes[0].states[0].anatomy_hold,undefined)
 p.mouth_preparation.anatomy_reviews[0].source_sha256=sha;assert.equal(JSON.stringify(p),before)
})
test('known bad anatomy freezes as preserved static source with honest finding, without blocking other production',()=>{
 const p={script:'same',audio_url:'same',structure:{image_style:'wuxia_webtoon',wuxia_ae_package:pkg(),wuxia_mouth_policy:policy,wuxia_motion_policy:{enabled:true},scenes:[{scene_number:1,image_effect:'zoom_in'}]}}
 const before=JSON.stringify(p);const t=freezeWuxiaScene({project_payload:p},1,[],0,2,24,{metadata:{}})
 assert.equal(t.states[0].sha256,sha);assert.equal(t.states[0].anatomy_hold.decision,'uncertain')
 assert(t.samples.every(s=>!s.motion?.active&&!s.ambient.length&&!s.mouths.length&&!s.effects.active?.length))
 assert.equal(JSON.stringify(p),before)
 const result=require('node:child_process').spawnSync(process.env.WUXIA_TEST_PYTHON||'python3',['-c',"import sys,json;sys.path.insert(0,'../worker');from wuxia_effects import validate_samples;from wuxia_motion import validate;t=json.load(sys.stdin);validate_samples(t);validate(t)"],{input:JSON.stringify(t),encoding:'utf8'})
 assert.equal(result.status,0,result.stderr)
})
test('polled anatomy findings reach the preview even without a final voice recording',()=>{
 const {mergeWuxiaMouthRefresh}=load('lib/stdWuxiaMouthRefresh.ts')
 const original=pkg(),report=original.mouth_preparation;delete original.mouth_preparation
 const p={id:'p',project_payload:{structure:{wuxia_ae_package:original,wuxia_mouth_policy:{...policy,auto_prepare:true,enabled:true}}}}
 const merged=mergeWuxiaMouthRefresh(p,{success:true,project_id:'p',audio_id:'not-bound',report,states:[]})
 assert.equal(withWuxiaAnatomyHolds(merged.project_payload.structure.wuxia_ae_package,policy).scenes[0].states[0].anatomy_hold.decision,'uncertain')
 assert.equal(p.project_payload.structure.wuxia_ae_package.mouth_preparation,undefined)
})
