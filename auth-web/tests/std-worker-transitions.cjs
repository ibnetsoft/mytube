const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript')
const e={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../lib/stdWorkerTransitions.ts'),'utf8'),{compilerOptions:{module:1,target:7}}).outputText)(e,require)
const row={transition_id:'T001',from_cut_id:'C001',to_cut_id:'C002',effect_label:'하드 컷',duration_seconds:0,reason:'원인과 결과',readiness:'direction_ready_pending_timeline_review'}
const project={project_payload:{structure:{cut_transition_plan:{contract:'manual_cut_transition_plan/v1',transitions:[row]}}}}
test('outgoing boundary is bound by explicit cut ID, never subtitle/scene index',()=>{
 assert.equal(e.workerTransitionForScene(project,{scene_number:1},1),null)
 assert.equal(e.workerTransitionForScene(project,{scene_number:15,cut_id:'C001'},15).to,'C002')
 assert.equal(e.workerTransitionForScene(project,{scene_number:15,cut_id:'C002'},15),null)
})
test('blocked sources and clip-internal cuts keep their truthful display state',()=>{
 for(const [change,state] of [[{blocked_cut_ids:['C002']},'blocked'],[{execution_owner:'video_clip_internal_edit'},'clip_internal']]){
  const p={source_payload:{pregenerated_structure:{cut_transition_plan:{contract:'manual_cut_transition_plan/v1',transitions:[{...row,...change}]}}}}
  assert.equal(e.workerTransitionList(p)[0].state,state)
 }
})
test('hard cuts remain visible with zero duration; invalid values and private metadata do not propagate',()=>{
 const p={project_payload:{cut_transition_plan:{contract:'manual_cut_transition_plan/v1',transitions:[{...row,source_image:'/private/secret.png'}, {...row,duration_seconds:NaN}]}}}
 assert.equal(e.workerTransitionList(p).length,1)
 assert.equal(e.workerTransitionList(p)[0].seconds,0)
 assert.equal(JSON.stringify(e.workerTransitionList(p)).includes('/private'),false)
})
test('conflicting explicit IDs do not attach a transition to the wrong scene',()=>{
 const p=structuredClone(project);p.project_payload.scenes=[{scene_number:15,cut_id:'C002'}]
 assert.equal(e.workerTransitionForScene(p,{scene_number:15,cut_id:'C001'},15),null)
})
