const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),load=require('./load-ts.cjs'),rig=load(path.resolve('lib/stdMotionRig.ts'))
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-6,`${a} != ${b}`)
test('key interpolation persists and honors hold boundaries and ease directions',()=>{
 const keys=[{t:0,value:0,interpolation:'ease-in'},{t:1,value:100}];near(rig.sampleValue(keys,.5),25);keys[0].interpolation='ease-out';near(rig.sampleValue(keys,.5),75);keys[0].interpolation='hold';near(rig.sampleValue(keys,.999),0);near(rig.sampleValue(keys,1),100);keys[0].interpolation='ease';near(rig.sampleValue(keys,.5),50)
 const r=rig.defaultRig();r.bones[0].keys=keys;assert.equal(rig.normalizeLayerAdvanced({rig:r}).rig.bones[0].keys[0].interpolation,'ease');r.bones[0].keys[0].interpolation='script';assert.throws(()=>rig.normalizeLayerAdvanced({rig:r}))
})
test('root translation preserves bind lengths and IK uses translated root coordinates',()=>{
 const r=rig.defaultRig();r.translation=[{t:0,x:0,y:0},{t:1,x:.1,y:.2}];r.bones[1].keys=rig.valueKeys(0);let q=rig.transform(rig.boneMatrices(r,1,200,100)[1],[100,80]);near(q[0],120);near(q[1],100)
 r.ik={root:0,child:1,bend:1,target:[{t:0,x:.7,y:.6},{t:1,x:.7,y:.6}]};q=rig.transform(rig.boneMatrices(r,1,200,100)[1],[100,80]);near(q[0],140);near(q[1],60);assert.deepEqual(rig.normalizeLayerAdvanced({rig:r}).rig.translation,r.translation)
})
test('joint limits constrain FK and IK, reversed limits fail validation',()=>{
 const r=rig.defaultRig();r.bones[0].limits={min:-10,max:10};r.bones[0].keys=rig.valueKeys(90);const m=rig.boneMatrices(r,1,100,100)[0];near(Math.atan2(m[1],m[0])*180/Math.PI,10)
 r.ik={root:0,child:1,bend:-1,target:[{t:0,x:1,y:0},{t:1,x:1,y:0}]};const a=rig.boneMatrices(r,1,100,100)[0];assert.ok(Math.abs(Math.atan2(a[1],a[0])*180/Math.PI)<=10.00001);r.bones[0].limits={min:20,max:10};assert.throws(()=>rig.normalizeLayerAdvanced({rig:r}))
})
test('locked pins anchor artwork against skeleton and moving pins regardless of pin order',()=>{
 const moving={position:[.5,.5],radius:.4,keys:[{t:0,x:.5,y:.5},{t:1,x:.7,y:.6}]},locked={...moving,locked:true};for(const pins of [[moving,locked],[locked,moving]]){const a={rig:rig.defaultRig(),mesh:{columns:16,rows:16,pins}};assert.deepEqual(rig.deformPoint([50,50],a,1,100,100),[50,50]);assert.equal(rig.normalizeLayerAdvanced(a).mesh.pins.find(p=>p.locked).locked,true)}
})
