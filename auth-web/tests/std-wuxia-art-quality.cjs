const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs')
const {withWuxiaAnatomyHolds}=load('lib/stdWuxiaArtQuality.ts'),{freezeWuxiaScene}=load('lib/stdWuxiaNative.ts'),sha='a'.repeat(64)

test('wuxia scenes without optional state direction can submit with the actual reviewed source',()=>{
 const scene={scene_number:1,cut_id:'C001',image_use_status:'approved',source_image_sha256:sha,gcs_bucket:'bucket',gcs_path:'source.png',anatomy_review:{contract:'wuxia_anatomy_review/v1',verdict:'pass',source_sha256:sha,cut_id:'C001'}}
 const project={project_payload:{image_style:'wuxia_webtoon',structure:{scenes:[scene]}}},source={asset_type:'image',metadata:{gcs_bucket:'bucket',gcs_path:'source.png'}}
 assert.equal(freezeWuxiaScene(project,1,[],0,2,24,source),null)
 assert.equal(source.metadata.sha256,sha,'Worker must verify exact reviewed source bytes')
 scene.image_use_status='review_candidate';assert.equal(freezeWuxiaScene(project,1,[],0,2,24,source),null)
 assert.equal(source.metadata.wuxia_anatomy_check.contract,'wuxia_source_anatomy/v1')
 assert.equal(source.metadata.wuxia_anatomy_check.excluded,false)
 scene.image_use_status='excluded';freezeWuxiaScene(project,1,[],0,2,24,source);assert.equal(source.metadata.wuxia_anatomy_check.excluded,true)
 source.metadata.gcs_path='replacement.png';assert.throws(()=>freezeWuxiaScene(project,1,[],0,2,24,source),/무결성/)

})
test('uploaded video does not require a nonexistent state direction package',()=>{
 const project={project_payload:{image_style:'wuxia_webtoon',structure:{scenes:[]}}}
 assert.equal(freezeWuxiaScene(project,1,[],0,2,24,{asset_type:'video',metadata:{gcs_bucket:'bucket',gcs_path:'source.mp4'}}),null)
})
const policy={anatomy_auto:{contract:'wuxia_anatomy_review/v1',enabled:true},energy_auto:{enabled:true,auto_prepare:true}}
const state={asset_id:'art',sha256:sha,start:0,end:1,face_exclusion_boxes:[],ambient_loops:[],dialogue_mouths:[],media_url:'/api/std/assets/gcs-file?bucket=test&path=art.png'}
const pkg=()=>({contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'E01_S01',preview_duration_seconds:2,states:[{...state}],graphics:[],effects:[]}],mouth_preparation:{anatomy_reviews:[{contract:'wuxia_anatomy_review/v1',asset_id:'art',source_sha256:sha,passed:false,decision:'uncertain',repair_request:{status:'reviewed_repair_request'}}]}})
test('only opted-in source-bound findings hold animation; original package is immutable',()=>{
 const p=pkg(),before=JSON.stringify(p);assert.equal(withWuxiaAnatomyHolds(p,{}).scenes[0].states[0].anatomy_hold.decision,'uncertain')
 assert.equal(withWuxiaAnatomyHolds(p,policy).scenes[0].states[0].anatomy_hold.decision,'uncertain')
 p.mouth_preparation.anatomy_reviews[0].source_sha256='b'.repeat(64);assert.equal(withWuxiaAnatomyHolds(p,policy).scenes[0].states[0].anatomy_hold.decision,'review_required')
 p.mouth_preparation.anatomy_reviews[0].source_sha256=sha;assert.equal(JSON.stringify(p),before)
})
test('known bad anatomy is excluded from web frames and native rendering',()=>{
 const p={script:'same',audio_url:'same',structure:{image_style:'wuxia_webtoon',wuxia_ae_package:pkg(),wuxia_mouth_policy:policy,scenes:[{scene_number:1}]}}
 const before=JSON.stringify(p),{wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts')
 assert.throws(()=>wuxiaSceneFrame({project_payload:p},1,[],0),/해부학/)
 assert.throws(()=>freezeWuxiaScene({project_payload:p},1,[],0,2,24,{metadata:{}}),/해부학/)
 assert.equal(JSON.stringify(p),before)
})
test('polled anatomy findings reach the preview even without a final voice recording',()=>{
 const {mergeWuxiaMouthRefresh}=load('lib/stdWuxiaMouthRefresh.ts')
 const original=pkg(),report=original.mouth_preparation;delete original.mouth_preparation
 const p={id:'p',project_payload:{structure:{wuxia_ae_package:original,wuxia_mouth_policy:{...policy,auto_prepare:true,enabled:true}}}}
 const merged=mergeWuxiaMouthRefresh(p,{success:true,project_id:'p',audio_id:'not-bound',report,states:[]})
 assert.equal(withWuxiaAnatomyHolds(merged.project_payload.structure.wuxia_ae_package,policy).scenes[0].states[0].anatomy_hold.decision,'uncertain')
 assert.equal(p.project_payload.structure.wuxia_ae_package.mouth_preparation,undefined)
})

test('only a reviewed replacement of the exact rejected source can be used',()=>{
 const p=pkg(),replacement={...state,sha256:'b'.repeat(64),media_url:'/api/std/assets/gcs-file?bucket=test&path=repair.png'}
 p.mouth_preparation.anatomy_replacements=[{original_source_sha256:sha,state:replacement}]
 assert(withWuxiaAnatomyHolds(p,policy).scenes[0].states[0].anatomy_hold)
 p.mouth_preparation.anatomy_reviews.push({contract:'wuxia_anatomy_review/v1',asset_id:'art',source_sha256:replacement.sha256,passed:true,decision:'passed'})
 const fixed=withWuxiaAnatomyHolds(p,policy).scenes[0].states[0]
 assert.equal(fixed.sha256,replacement.sha256);assert.equal(fixed.anatomy_hold,undefined)
 p.scenes[0].states[0].sha256='c'.repeat(64)
 assert.equal(withWuxiaAnatomyHolds(p,policy).scenes[0].states[0].anatomy_hold.decision,'review_required')
})
