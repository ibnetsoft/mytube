const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript')
const source=fs.readFileSync(path.resolve(__dirname,'../lib/stdSceneDirection.ts'),'utf8'),exportsObject={}
new Function('exports','require',ts.transpileModule(source,{compilerOptions:{module:1,target:7}}).outputText)(exportsObject,require)

test('subtitle scene eye icon follows only enabled directing plans with exact cues',()=>{
 const plan={enabled:true,character:'お鈴',cues:[{at_seconds:2.4,duration_seconds:.11,type:'single'}]}
 const scenes=[{scene_number:25,scene_direction_plan:{eye_blink_plan:plan}},
  {scene_number:26,scene_direction_plan:{eye_blink_plan:{enabled:false,cues:[]}}}]
 assert.equal(exportsObject.directedEyeBlinkPlan(scenes,25),plan)
 assert.equal(exportsObject.directedEyeBlinkPlan(scenes,26),null)
 assert.equal(exportsObject.directedEyeBlinkPlan(scenes,27),null)
})

test('legacy AE direction and nested metadata remain readable',()=>{
 const plan={enabled:true,cues:[{at_seconds:1,type:'single'}]}
 assert.equal(exportsObject.directedEyeBlinkPlan([{scene_order:19,metadata:{ae_directorial_plan:{eye_blink_plan:plan}}}],19),plan)
})

test('direction badges expose planned, verified and review states in a stable order',()=>{
 const scene={scene_number:25,scene_direction_plan:{
  eye_blink_plan:{enabled:true,character:'お鈴',cues:[{at_seconds:2.4}]},
  ae_operations:['camera_move','depth_parallax','light_flicker','atmosphere_drift'],
  required_layers:['background','character','foreground'],focus_target:{reason:'speaker face'}},
  metadata:{cowork_image_asset:{speaker_geometry:{eye_blink:{state:'ready'},speakers:[
   {speaker:'お鈴',status:'visible',mouth_box:[.4,.4,.45,.43]}]}},psd_layer_asset:{qa_status:'pending'}}}
 const badges=exportsObject.sceneDirectionBadges([scene],25)
 assert.deepEqual(badges.map(b=>[b.kind,b.state]),[
  ['eye','verified'],['review','needs_review'],['mouth','verified'],['parallax','needs_review'],
  ['camera','planned'],['light','planned'],['atmosphere','planned']])
 assert.match(badges[0].detail,/2.4초/);assert.match(badges[1].detail,/패럴랙스/)
})

test('layer icon requires the complete approved GCS layer receipt',()=>{
 const asset={source:'independently_authored_png_layers',storage_provider:'gcs',gcs_bucket:'air-assets',
  gcs_path:'topics/t1/layers/scene-025-a.psd',sha256:'a'.repeat(64),layers:['background','character','foreground'],
  qa_status:'approved',review:{reviewer:'worker',reviewed_at:'2026-10-10T00:00:00Z'}}
 const complete={scene_number:25,psd_layer_status:'ready',metadata:{psd_layer_asset:asset}}
 assert.equal(exportsObject.hasApprovedGcsLayerAsset(complete),true)
 assert.deepEqual(exportsObject.sceneDirectionBadges([complete],25).map(b=>[b.kind,b.state]),[['layer','verified']])
 for(const incomplete of [
  {...complete,psd_layer_status:'pending'},
  {...complete,metadata:{psd_layer_asset:{...asset,gcs_path:''}}},
  {...complete,metadata:{psd_layer_asset:{...asset,sha256:''}}},
  {...complete,metadata:{psd_layer_asset:{...asset,qa_status:'pending'}}},
  {...complete,metadata:{psd_layer_asset:{...asset,review:null}}},
 ]) assert.equal(exportsObject.sceneDirectionBadges([incomplete],25).some(b=>b.kind==='layer'),false)
})

test('scenes without saved direction or geometry show no badges',()=>{
 assert.deepEqual(exportsObject.sceneDirectionBadges([{scene_number:25}],25),[])
})
