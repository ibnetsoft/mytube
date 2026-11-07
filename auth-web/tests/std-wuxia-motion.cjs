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
test('new automatic policy freezes fixed scenes for actual review too, and preserves the scene selection',()=>{
 const f=fixture('none');f.project.project_payload.structure.wuxia_motion_policy={contract:'wuxia_motion_auto/v1',enabled:true,actual_source_review_required:true,actual_output_review_required:true};
 f.project.project_payload.structure.scenes[0].wuxia_motion_selection={reason:'대사 가독성을 위한 고정',basis:'planned_visuals'};
 const t=freezeWuxiaScene(f.project,1,[],0,4,24,{metadata:{}});
 assert.equal(t.contract,'wuxia_native_timeline/v5');assert.equal(t.motion_selection.reason,'대사 가독성을 위한 고정');assert.equal(t.auto_motion_policy.actual_output_review_required,true);
 assert.ok(t.samples.every(s=>Object.keys(s.motion).length===0));
});
test('automatic fixed-scene review fits the existing snapshot budget for a ten-minute clock',()=>{
 const f=fixture('none');f.project.project_payload.structure.wuxia_motion_policy={contract:'wuxia_motion_auto/v1',enabled:true,actual_output_review_required:true};
 f.project.project_payload.structure.scenes[0].transition_effect='none';
 f.project.project_payload.structure.wuxia_ae_package.scenes[0].preview_duration_seconds=600;
 const t=freezeWuxiaScene(f.project,1,[],0,600,24,{metadata:{}});
 assert.equal(t.samples.length,14400);assert.ok(Buffer.byteLength(JSON.stringify(t))<3_000_000);
 assert.ok(t.samples.every(s=>!('transition' in s)&&Object.keys(s.motion).length===0));
});
test('a reviewed torch cut alone refracts the approved top rows; earlier face cuts remain untouched',()=>{
 const f=fixture('none+heat'),sc=f.project.project_payload.structure.wuxia_ae_package.scenes[0];
 f.state.end=.5;f.state.heat_shimmer_enabled=false;delete f.state.face_exclusion_boxes;
 sc.states.push({...f.state,asset_id:'b',sha256:'b'.repeat(64),media_url:'/api/std/media?bucket=b&path=b.png',start:.5,end:1,heat_shimmer_enabled:true,heat_shimmer_vertical_range:[0,.2],face_exclusion_boxes:[],hand_exclusion_boxes:[[.3,.2,.9,.8]]});
 assert.deepEqual(f.at(.5).motion.heat,[]);const hot=f.at(2.5).motion.heat;assert.ok(hot.some(v=>v!==0));assert.ok(hot.slice(10).every(v=>v===0));
 const frozen=freezeWuxiaScene(f.project,1,[],0,4,24,{metadata:{}});assert.equal(frozen.states[1].heat_face_reviewed,true);assert.ok(frozen.samples.some(s=>s.state==='b'&&s.motion.heat.some(x=>x)));
});
test('source-reviewed camera strength reduces overscan without changing the opening movement clock',()=>{
 const f=fixture('pan_left');f.project.project_payload.structure.wuxia_ae_package.scenes[0].motion_strength=.4;
 assert.equal(f.at(1).motion.scale,1.048);assert.equal(f.at(1).motion.dx,-.012);assert.deepEqual(f.at(1).motion,f.at(3).motion);
 f.project.project_payload.structure.wuxia_ae_package.scenes[0].motion_strength=2;assert.match(f.at(.5).motion.issues[0],/invalid_motion_strength/);
});
test('energy-only state preserves anatomy and heat/camera holds on every frame through nine seconds',()=>{
 const f=fixture('pan_right_zoom_in+heat'),sc=f.project.project_payload.structure.wuxia_ae_package.scenes[0];
 sc.preview_duration_seconds=9;sc.effects=[{type:'impact_shake'}];f.state.energy_only_motion=true;
 for(const sec of [0,.5,1,4.5,8.99]){
  const frame=f.at(sec);assert.equal(frame.motion.active,false);assert.equal(frame.motion.dx,0);assert.equal(frame.motion.scale,1);assert.deepEqual(frame.motion.heat,[]);
  assert.deepEqual(frame.effects.active,[]);assert.deepEqual(frame.mouths,[]);
 }
 const native=freezeWuxiaScene(f.project,1,[],0,9,24,{metadata:{}});assert.equal(native.samples.length,216);
 assert.ok(native.samples.every(s=>!s.motion||!s.motion.active));
});
test('new energy automation waits for actual source review before freezing; absent is valid',()=>{
 const f=fixture('none');f.project.project_payload.structure.wuxia_mouth_policy={energy_auto:{enabled:true,auto_prepare:true}};
 assert.throws(()=>freezeWuxiaScene(f.project,1,[],0,4,24,{metadata:{}}),/기운 검토/);
 f.state.energy_preparation={source_sha256:f.state.sha256,decision:'absent'};
 assert.equal(freezeWuxiaScene(f.project,1,[],0,4,24,{metadata:{}}).states.length,1);
});
