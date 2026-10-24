const assert=require('node:assert/strict'),path=require('node:path')
const {bindSceneDirection,recordedDirectionFingerprint,assertRecordedSceneDirections}=require('./load-ts.cjs')(path.join(__dirname,'../lib/stdSceneExecution.ts'))
const direction={contract:'scene_direction_plan/v2',visual_strategy:'Reveal the letter',execution_design:{
 camera:{kind:'push',keys:[{t:0,x:.5,y:.5,scale:1,rotation:0,opacity:100},{t:1,x:.5,y:.5,scale:1.03,rotation:0,opacity:100}]},
 cue:{quote:'手紙',phase:'during'},effects:[{type:'light_sweep',reason:'A reflection crosses the letter.',intensity:.24,center:[.61,.48],radius:.18,color:[1,.8,.45],event:{quote:'手紙',phase:'during',at:'middle',duration_seconds:.4}}],
 transition:{kind:'crossfade',duration_seconds:.22,reason:'Blend the discovery into the reaction.'},graphics:{speech_bubbles:false,speedlines:false}}}
const rows=[{text:'彼は',start:10,end:12},{text:'手',start:12,end:13},{text:'紙を見た。',start:13,end:16}]
const original=JSON.stringify(direction)
const result=bindSceneDirection(direction,'image',rows,10,20,24)
assert.deepEqual(result.keys.map(k=>k.t),[0,.2,.6,1])
assert.equal(result.keys.at(-1).scale,1.03)
assert.equal(result.effects.length,1)
assert.equal(result.effects[0].type,'light_sweep')
assert.ok(Math.abs(result.effects[0].start-.38)<1e-9)
assert.ok(Math.abs(result.effects[0].end-.42)<1e-9)
assert.equal(result.transition,'crossfade')
assert.equal(result.transition_seconds,.22)
assert.equal(JSON.stringify(direction),original)
assert.equal(bindSceneDirection({contract:'scene_direction_plan/v1'},'image',[],0,1,24),null)
assert.throws(()=>bindSceneDirection(direction,'image',[{text:'違う文',start:10,end:20}],10,20,24),/最終|최종/)
const graphic=structuredClone(direction);graphic.execution_design.graphics.speech_bubbles=true
assert.throws(()=>bindSceneDirection(graphic,'image',rows,10,20,24),/그래픽/)
console.log('Scene direction: recorded subtitle cue binding, split phrases, legacy isolation and graphic rejection passed')
const payload={subtitle_source_audio_id:'voice',subtitles:rows.map(r=>({...r,scene_number:1})),structure:{scenes:[{scene_number:1,scene_direction_plan:direction,ae_motion_plan:{enabled:true},metadata:{}}]}}
assert.throws(()=>assertRecordedSceneDirections({project_payload:payload}),/검수/)
payload.structure.scenes[0].metadata.ae_motion_asset={status:'ready',ae_reviewed:true,render_sha256:'a'.repeat(64),source_direction_review:{passed:true},recorded_direction_binding:{fingerprint:recordedDirectionFingerprint(payload,1)}}
assertRecordedSceneDirections({project_payload:payload})
payload.subtitles[1].end=13.2
assert.throws(()=>assertRecordedSceneDirections({project_payload:payload}),/검수/)
assertRecordedSceneDirections({project_payload:{structure:{scenes:[{scene_direction_plan:{contract:'scene_direction_plan/v1'}}]}}})
