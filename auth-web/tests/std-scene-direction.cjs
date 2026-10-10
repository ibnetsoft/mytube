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
