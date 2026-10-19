const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),load=require('./load-ts.cjs')
const rig=load(path.resolve('lib/stdMotionRig.ts')),motion=load(path.resolve('lib/stdMotionStudio.ts'))
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-5,`${a} != ${b}`)
test('parent rotation carries the child pivot and composes child rotation',()=>{
 const r=rig.defaultRig();r.bones[0].keys=rig.valueKeys(90);r.bones[1].keys=rig.valueKeys(-90)
 const matrices=rig.boneMatrices(r,1,100,100),elbow=rig.transform(matrices[0],[50,50]),wrist=rig.transform(matrices[1],[50,80])
 near(elbow[0],20);near(elbow[1],20);near(wrist[0],20);near(wrist[1],50)
})
test('IK reaches both bend directions, clamps unreachable targets and supports rectangular artwork',()=>{
 for(const bend of [1,-1]){const r=rig.defaultRig();r.ik={root:0,child:1,bend,target:[{t:0,x:.7,y:.5},{t:1,x:.7,y:.5}]};const endpoint=rig.transform(rig.boneMatrices(r,.5,200,100)[1],[100,80]);near(endpoint[0],140);near(endpoint[1],50)
 r.ik.target=[{t:0,x:2,y:2},{t:1,x:2,y:2}];const far=rig.transform(rig.boneMatrices(r,1,200,100)[1],[100,80]);near(Math.hypot(far[0]-100,far[1]-20),60)}
})
test('mesh pins move only within their influence and preserve the bind pose',()=>{
 const advanced={mesh:{columns:16,rows:16,pins:[{position:[.5,.5],radius:.25,keys:[{t:0,x:.5,y:.5},{t:1,x:.6,y:.7}]}]}}
 assert.deepEqual(rig.deformPoint([50,50],advanced,0,100,100),[50,50]);assert.deepEqual(rig.deformPoint([50,50],advanced,1,100,100),[60,70]);assert.deepEqual(rig.deformPoint([0,0],advanced,1,100,100),[0,0])
})
test('advanced web recipes persist independently of existing AE recipes',()=>{
 const original={version:1,enabled:true,aspect:'16:9',fps:24,scenes:{1:motion.motionPreset('impact')}}
 const studio=motion.switchMotionProduction(original,'motion_studio');studio.scenes[1]={...motion.motionScene(),source:'psd',layers:{character:{depth:0,keys:[motion.motionKey(0),motion.motionKey(1)],advanced:{rig:rig.defaultRig(),effects:[rig.nativeEffect('glow')]}}},native:{effects:[rig.nativeEffect('fractal_noise')],paths:[]}}
 const normalized=motion.normalizeMotionDraft(studio),ae=motion.switchMotionProduction(normalized,'ae');assert.deepEqual(ae.scenes,original.scenes);assert.deepEqual(motion.switchMotionProduction(ae,'motion_studio').scenes,normalized.scenes)
})
test('invalid hierarchies, cycles, collapsed bones, excessive meshes, unbounded poses and unknown effects fail closed',()=>{
 for(const mutate of [r=>r.bones[0].parent=1,r=>r.bones[1].parent=1,r=>r.bones[1].end=r.bones[1].start,r=>r.bones[1].keys[1].value=NaN,r=>r.bones[0].keys.reverse()]){const r=rig.defaultRig();mutate(r);assert.throws(()=>rig.normalizeLayerAdvanced({rig:r}))}
 assert.throws(()=>rig.normalizeLayerAdvanced({mesh:{columns:1000,rows:16,pins:[]}}));assert.throws(()=>rig.normalizeNativeEffects([{...rig.nativeEffect('glow'),type:'arbitrary-plugin'}]))
 const r=rig.defaultRig();r.ik={root:1,child:0,bend:1,target:[{t:0,x:.5,y:.5},{t:1,x:.5,y:.5}]};assert.throws(()=>rig.normalizeLayerAdvanced({rig:r}))
})
test('glow threshold settings persist and reject unbounded or unrelated effect parameters',()=>{
 const e={...rig.nativeEffect('glow'),glow:{threshold:.72,softKnee:.2,basedOn:'alpha'}};assert.deepEqual(rig.normalizeNativeEffects([e])[0].glow,e.glow)
 for(const glow of [{...e.glow,threshold:NaN},{...e.glow,softKnee:2},{...e.glow,basedOn:'script'}])assert.throws(()=>rig.normalizeNativeEffects([{...e,glow}]))
 assert.throws(()=>rig.normalizeNativeEffects([{...e,type:'blur'}]))
})
