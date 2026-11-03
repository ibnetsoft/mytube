const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs')
const {resolveSceneMedia}=load('lib/stdSceneMedia.ts'),{projectContentIdentity}=load('lib/stdContentIdentity.ts')
test('revision media selection requires the chosen videos and keeps other scenes still',()=>{
 const project={id:'p',topic_queue_id:1,project_payload:{script:'new',strict_content_identity:true,structure:{required_video_scene_count:18,motion_graphic_video_scenes:[19,60,70]}}}
 const hash=projectContentIdentity(project).script_sha256
 const asset=(n,type,id,revision=hash,date='2026-01-01')=>({id,scene_number:n,asset_type:type,status:'assigned',created_at:date,metadata:{content_identity:{script_sha256:revision}}})
 for(const n of [1,18,19,60,70]){
  const image=asset(n,'image','image'),old=asset(n,'video','old','old'),video=asset(n,'video','current')
  assert.throws(()=>resolveSceneMedia(project,{scene_number:n},[image,old]),/requires video/)
  assert.equal(resolveSceneMedia(project,{scene_number:n},[image,old,video]).id,'current')
 }
 for(const n of [20,50,101]){
  const image=asset(n,'image','image'),video=asset(n,'video','stray')
  assert.equal(resolveSceneMedia(project,{scene_number:n},[image,video]).id,'image')
  assert.throws(()=>resolveSceneMedia(project,{scene_number:n},[video]),/requires image/)
 }
 const old=asset(20,'image','old-current',hash,'2026-01-01'),newer=asset(20,'image','new-current',hash,'2026-02-01')
 assert.equal(resolveSceneMedia(project,{scene_number:20},[old,newer]).id,'new-current')
})
