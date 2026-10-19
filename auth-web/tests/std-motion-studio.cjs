const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path')
const load=require('./load-ts.cjs'),lib=load(path.resolve('lib/stdMotionStudio.ts'))
const draft=(aspect='9:16')=>({version:1,enabled:true,aspect,fps:24,scenes:{'1':lib.motionScene()}})
test('validated motion project locks output orientation and interpolation',()=>{
 const value=lib.normalizeMotionDraft(draft())
 const project={project_payload:{render_settings:{motion:value}}}
 assert.equal(lib.motionOutputAspect(project),'9:16')
 assert.equal(lib.motionForProject(project).enabled,true)
 const keys=lib.motionPreset('push').keys
 assert.equal(lib.interpolateMotion(keys,.5).scale,1.04)
 for(const aspect of ['16:9','9:16'])assert.equal(lib.normalizeMotionDraft(draft(aspect)).aspect,aspect)
})
test('invalid times, scene keys and unsupported distortion cannot reach worker',()=>{
 for(const change of [v=>v.scenes[1].keys.reverse(),v=>v.scenes[1].keys[0].x=NaN,v=>v.aspect='1:1',v=>v.scenes[1].keys[1].scale=9,v=>v.scenes.bad=lib.motionScene()]){const v=draft();change(v);assert.throws(()=>lib.normalizeMotionDraft(v))}
})
test('every preset carries editable supported effects and preserves source choice',()=>{
 for(const preset of lib.MOTION_PRESETS){const v=draft();v.scenes[1]=lib.motionPreset(preset.id,{...lib.motionScene(),source:'video'});assert.equal(lib.normalizeMotionDraft(v).scenes[1].source,'video')}
})
test('PSD layer keys preserve authored depth and cannot be moved outside bounded artwork space',()=>{
 const v=draft();v.scenes[1].source='psd';v.scenes[1].layers={hair:{depth:.3,keys:[lib.motionKey(0),{...lib.motionKey(1),x:.52,rotation:2}]}}
 assert.equal(lib.normalizeMotionDraft(v).scenes[1].layers.hair.depth,.3)
 v.scenes[1].layers.hair.keys[1].x=.8;assert.throws(()=>lib.normalizeMotionDraft(v))
})

test('web hybrid assignments survive save and reject invalid provider references or insert times',()=>{
 const v=draft();v.web={mode:'hybrid',inserts:{'1':{job_id:'12345678-1234-5123-a123-123456789012',start:.5,duration:3}}}
 assert.deepEqual(lib.normalizeMotionDraft(v).web,v.web)
 v.web.inserts[1].start=-1;assert.throws(()=>lib.normalizeMotionDraft(v));v.web.inserts[1].start=0
 v.web.inserts[1].job_id='https://arbitrary.example/';assert.throws(()=>lib.normalizeMotionDraft(v))
})
