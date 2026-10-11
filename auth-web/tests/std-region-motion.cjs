const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript')
const ex={};new Function('exports',ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../lib/stdRegionMotion.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText)(ex)
const timeline=ex.motionSceneTimeline([{id:'a',text:'first',scene_number:63,start_num:600,end_num:603},{id:'b',text:'next',scene_number:63,start_num:603,end_num:608}],63)
const region={id:'arm',name:'팔',polygon:[[.2,.2],[.4,.2],[.4,.6],[.2,.6]],anchor:[.3,.2],action:'rotate',amplitude:12,period:2,cycles:2,subtitleId:'b',start:999}
test('saved subtitle timing determines region start and scene duration',()=>{assert.equal(timeline.duration,8);assert.equal(ex.validateRegionMotions([region],timeline)[0].start,3)})
test('bounded natural commands become editable settings, never arbitrary executable code',()=>{assert.deepEqual(ex.parseRegionMotionCommand('좌우로 3%씩 2초마다 3번 반복'),{action:'horizontal',amplitude:3,period:2,cycles:3});assert.equal(ex.parseRegionMotionCommand('팔을 15도 회전, 1초마다 4번').action,'rotate');assert.equal(ex.parseRegionMotionCommand('팔꿈치를 구부려').action,'bend');assert.equal(ex.parseRegionMotionCommand('걷기 25도 1초마다 3번').action,'walk');assert.throws(()=>ex.parseRegionMotionCommand('delete all layers'))})
test('rejects changed subtitle, excessive duration, malformed region and unsupported motion',()=>{for(const patch of [{subtitleId:'missing'},{period:10},{action:'script'},{amplitude:NaN},{polygon:[]},{anchor:[-1,.5]},{cycles:2.5}])assert.throws(()=>ex.validateRegionMotions([{...region,...patch}],timeline));assert.throws(()=>ex.validateRegionMotions([region,region],timeline))})
test('cycles return to rest before and after the selected subtitle range',()=>{const r=ex.validateRegionMotions([region],timeline)[0];assert.equal(ex.motionPhase(r,0),0);assert.equal(ex.motionPhase(r,3.5),1);assert.equal(ex.motionPhase(r,4.5),-1);assert.equal(ex.motionPhase(r,7),0)})

test('joint chains reject missing parents and cycles; supports full character rigs',()=>{
 const root={...region,id:'body',action:'hold',subtitleId:'a',period:2,cycles:1};
 const child={...root,id:'arm',parentId:'body',action:'bend'};
 assert.equal(ex.validateRegionMotions([child,root],timeline)[0].parentId,'body');
 for(const patch of [{parentId:'missing'},{parentId:'arm'},{parentId:''},{phaseOffset:2},{restAngle:181}])assert.throws(()=>ex.validateRegionMotions([root,{...child,...patch}],timeline));
 assert.throws(()=>ex.validateRegionMotions([{...root,parentId:'arm'},child],timeline));
 assert.equal(ex.validateRegionMotions(Array.from({length:32},(_,i)=>({...root,id:'part'+i})),timeline).length,32);
});
test('joint pivots remain attached when the parent turns, irrespective of array order',()=>{
 const root={...region,id:'body',action:'rotate',start:0,amplitude:90};
 const child={...root,id:'arm',parentId:'body',action:'bend',anchor:[.3,.5],amplitude:30};
 const size=[1000,600], t=.5, matrix=ex.regionTransform([child,root],'arm',t,size), parent=ex.regionTransform([child,root],'body',t,size);
 const apply=(m,x,y)=>[m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5]];
 const pivot=apply(matrix,300,300), expected=apply(parent,300,300);
 pivot.forEach((v,i)=>assert.ok(Math.abs(v-expected[i])<1e-8));
});
test('walking alternates sides and knees bend only in one direction',()=>{
 const leg={...region,action:'walk',start:0,walkPart:'upper'};
 assert.ok(ex.motionAngle(leg,.5)>0);assert.ok(ex.motionAngle({...leg,phaseOffset:.5},.5)<0);
 assert.equal(ex.motionAngle({...leg,walkPart:'lower'},1.5),0);
 assert.ok(ex.motionAngle({...leg,walkPart:'lower'},.5)>0);
 assert.equal(ex.motionAngle(leg,4),0);
});
test('rig changes reuse the approved artwork identity',()=>{
 const key=ex.regionLayerKey('image','sha',[region]);
 assert.equal(key,ex.regionLayerKey('image','sha',[{...region,parentId:'body',action:'walk',phaseOffset:.5,restAngle:12,walkPart:'lower'}]));
});
