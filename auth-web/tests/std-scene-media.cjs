const test=require('node:test'),assert=require('node:assert/strict')
const load=require('./load-ts-module.cjs')
const {resolveSceneMedia}=load('lib/stdSceneMedia.ts')
function fixture(motion='still') {
 const project={project_payload:{submission_pipeline_version:2,render_settings:{comic:{version:1,mode:'moving_comic',panels:{'1':{motion}}}},structure:{scenes:[]}}}
 const scene={scene_number:1}
 const image={id:'image',scene_number:1,asset_type:'image',status:'uploaded',metadata:{gcs_bucket:'bucket',gcs_path:'image.png'}}
 const video={id:'video',scene_number:1,asset_type:'video',status:'uploaded',metadata:{gcs_bucket:'bucket',gcs_path:'video.mp4'}}
 return {project,scene,image,video}
}
test('comic still and pan select the image even when a generated video exists',()=> {
 for(const motion of ['still','pan']) {
  const f=fixture(motion)
  assert.equal(resolveSceneMedia(f.project,f.scene,[f.video,f.image]).id,'image')
 }
 const f=fixture('video')
 assert.equal(resolveSceneMedia(f.project,f.scene,[f.image,f.video]).id,'video')
})
test('reviewed postprocessing replaces exactly its selected source and stale processing cannot switch a comic still to video',()=> {
 const f=fixture()
 const processed={status:'ready',gcs_bucket:'bucket',gcs_path:'reviewed.mp4',render_sha256:'a'.repeat(64),source_image:{object_path:'image.png'}}
 f.project.project_payload.structure.scenes=[{scene_number:1,ae_motion_plan:{enabled:true},metadata:{ae_motion_asset:processed}}]
 assert.equal(resolveSceneMedia(f.project,f.scene,[f.video,f.image]).metadata.gcs_path,'reviewed.mp4')
 processed.source_image.object_path='old-source.png'
 assert.equal(resolveSceneMedia(f.project,f.scene,[f.video,f.image]).id,'image')
})
test('resolved source honors actual current asset order and reviewed output override',()=> {
 const f=fixture('video'), older={...f.video,id:'older',created_at:'2026-10-16'}, newer={...f.video,id:'newer',created_at:'2026-10-17'}
 assert.equal(resolveSceneMedia(f.project,f.scene,[older,f.image,newer]).id,'newer')
 const reviewed={id:'ae-output',asset_type:'video'}
 assert.equal(resolveSceneMedia(f.project,f.scene,[],reviewed),reviewed)
 assert.throws(()=>resolveSceneMedia(f.project,f.scene,[f.video,f.image],
  {...reviewed,metadata:{source_image:{object_path:'replaced-video.mp4'}}}),/원본 자산/)
 assert.equal(resolveSceneMedia(f.project,f.scene,[f.video,f.image],
  {...reviewed,metadata:{source_image:{object_path:'video.mp4'}}}).id,'ae-output')
})
