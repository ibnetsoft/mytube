const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs')
const {savedStdVisualStepStatus}=load('lib/stdVisualStepStatus.ts'),identity=load('lib/stdContentIdentity.ts')
test('revisioned visual status requires current selected motion video and a still elsewhere',()=>{
 const project={id:'p',topic_queue_id:1,project_payload:{script:'new',strict_content_identity:true,structure:{required_video_scene_count:0,motion_graphic_video_scenes:[19],scenes:[{scene_number:19,video_url:'old'},{scene_number:20,image_url:'old'}]}}}
 const hash=identity.projectContentIdentity(project).script_sha256
 project.project_payload.content_identity={script_sha256:hash}
 const asset=(n,type,sha)=>({id:`${n}-${type}`,scene_number:n,asset_type:type,status:'assigned',metadata:{gcs_path:'file',content_identity:{script_sha256:sha}}})
 const assets=[asset(19,'video','old'),asset(19,'image',hash),asset(20,'image',hash)]
 let result=savedStdVisualStepStatus(project,assets);assert.equal(result.isImageDone,false);assert.equal(result.isVideoStepDone,false)
 assets.push(asset(19,'video',hash));result=savedStdVisualStepStatus(project,assets);assert.equal(result.isImageDone,true);assert.equal(result.isVideoStepDone,true)
})
