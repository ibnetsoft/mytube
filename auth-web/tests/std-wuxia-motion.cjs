const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts'),{freezeWuxiaScene}=load('lib/stdWuxiaNative.ts');
const {WUXIA_MOTIONS,splitWuxiaMotion,joinWuxiaMotion}=load('lib/stdWuxiaMotion.ts');
function fixture(value){
 const state={asset_id:'a',sha256:'a'.repeat(64),media_url:'/api/std/media?bucket=b&path=a.png',start:0,end:1,face_exclusion_boxes:[[.3,.25,.6,.55]]};
 const project={project_payload:{structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'S001',preview_duration_seconds:4,states:[state],graphics:[]}]},scenes:[{scene_number:1,image_effect:value,transition_effect:'flash'}]}}};
 return {project,state,at:t=>wuxiaSceneFrame(project,1,[],t,24)};
}
test('four camera directions support both zoom directions and settle before the scene ends',()=>{
 for(const pan of ['pan_left','pan_right','pan_up','pan_down'])for(const zoom of ['none','zoom_in','zoom_out']){
  const f=fixture(joinWuxiaMotion(pan,zoom,false)),a=f.at(0).motion,b=f.at(1).motion,c=f.at(3).motion;
  const axis=pan==='pan_left'||pan==='pan_right'?'dx':'dy';assert.equal(Math.sign(b[axis]-a[axis]),pan==='pan_right'||pan==='pan_down'?1:-1);
  if(zoom!=='none')assert.equal(Math.sign(b.scale-a.scale),zoom==='zoom_in'?1:-1);
  assert.deepEqual(b,c);assert.ok(a.scale>=1&&b.scale>=1);
 }
 for(const id of WUXIA_MOTIONS.map(m=>m.id))assert.equal(splitWuxiaMotion(id+'+heat').valid,true);
});
test('heat refracts space with independent band phases and preserves reviewed face rows',()=>{
 const f=fixture('none+heat'),a=f.at(.5).motion,b=f.at(.9).motion;
 assert.equal(a.heat.length,48);assert.notDeepEqual(a.heat,b.heat);assert.ok(new Set(a.heat).size>5);
 for(let i=0;i<48;i++)if(i/48<.575&&(i+1)/48>.225)assert.equal(a.heat[i],0);
 assert.deepEqual(f.at(.5).motion,a);assert.ok(a.heat.every(x=>Math.abs(x)<=5));assert.equal(a.dx,0);assert.equal(a.scale,1);
 f.state.face_exclusion_boxes=undefined;assert.match(f.at(.5).motion.issues[0],/missing_heat_face_review/);
});
test('camera, heat and transition freeze to v5 on the same clock without changing voice or scene length',()=>{
 const f=fixture('pan_right_zoom_out+heat'),t=freezeWuxiaScene(f.project,1,[],0,4,24,{metadata:{}});
 assert.equal(t.contract,'wuxia_native_timeline/v5');assert.equal(t.samples.length,96);assert.equal(t.states[0].heat_face_reviewed,true);
 assert.deepEqual(t.states[0].heat_protection_boxes,f.state.face_exclusion_boxes);
 for(const s of t.samples){assert.deepEqual(s.motion,f.at(s.at).motion);assert.equal(s.transition.kind,'flash')}
 assert.equal(t.samples.at(-1).at,95/24);
});
test('invalid motion and unreviewed heat cannot silently render as a fixed camera',()=>{
 const f=fixture('pan_mystery');assert.throws(()=>freezeWuxiaScene(f.project,1,[],0,4,24,{metadata:{}}),/이미지 모션 검증/);
 const g=fixture('none+heat');delete g.state.face_exclusion_boxes;assert.throws(()=>freezeWuxiaScene(g.project,1,[],0,4,24,{metadata:{}}),/missing_heat/);
});
