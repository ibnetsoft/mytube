const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts');
const {freezeWuxiaScene}=load('lib/stdWuxiaNative.ts');
function fixture(kind){
 const state=(id)=>({asset_id:id,sha256:(id==='a'?'a':'b').repeat(64),media_url:`/api/std/media?bucket=b&path=${id}.png`,start:0,end:1});
 const scenes=[{scene_id:'S001',preview_duration_seconds:2,states:[state('a')],graphics:[]},{scene_id:'S002',preview_duration_seconds:2,states:[state('b')],graphics:[]}];
 const project={project_payload:{structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes},scenes:[{scene_number:2,metadata:{transition_effect:kind}}]}}};
 return {project,at:t=>wuxiaSceneFrame(project,2,[],2+t,24)};
}
test('slide enters over the preceding still and pause/backward seek use the exact same clock',()=>{
 const f=fixture('wipe_left');assert.equal(f.at(0).transition.dx,1);assert.equal(f.at(0).transition.source.asset_id,'a');
 const middle=f.at(.125);assert.ok(middle.transition.dx>0&&middle.transition.dx<1);f.at(1);assert.deepEqual(f.at(.125),middle);
 assert.equal(f.at(.5).transition.dx,0);assert.equal(f.at(.5).transition.backdrop,0);
});
test('flash, punch, snap, dissolve and closing fade are short and return to identity',()=>{
 for(const kind of ['flash','punch','snap_shake','dissolve']){
  const f=fixture(kind);assert.notDeepEqual(f.at(.042).transition,f.at(.5).transition);
  const t=f.at(.5).transition;assert.deepEqual([t.dx,t.dy,t.scale,t.opacity,t.flash],[0,0,1,1,0]);
 }
 assert.ok(fixture('fade_out').at(1.9).transition.opacity<1);
 assert.equal(fixture('none').at(0).transition.source,null);
});
test('frozen output carries v4, SHA-bound preceding art and frame-for-frame editor poses without changing timing',()=>{
 const f=fixture('wipe_up'),t=freezeWuxiaScene(f.project,2,[],2,4,24,{metadata:{}});
 assert.equal(t.contract,'wuxia_native_timeline/v4');assert.equal(t.transition_source.sha256,'a'.repeat(64));assert.equal(t.samples.length,48);
 for(const s of t.samples){const {source,...expected}=f.at(s.at).transition;assert.deepEqual(s.transition,expected)}
 assert.equal(t.samples[0].at,0);assert.equal(t.samples.at(-1).at,47/24);
});
test('unsupported transitions and changed source identity fail rather than disappearing in the renderer',()=>{
 const f=fixture('morph');assert.match(f.at(0).transition.issues[0],/unsupported/);
 assert.throws(()=>freezeWuxiaScene(f.project,2,[],2,4,24,{metadata:{}}),/전환 검증/);
 const g=fixture('dissolve');g.project.project_payload.structure.wuxia_ae_package.scenes[0].states[0].sha256='bad';
 assert.throws(()=>freezeWuxiaScene(g.project,2,[],2,4,24,{metadata:{}}),/저장 위치/);
});
