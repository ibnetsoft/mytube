const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {wuxiaEffectFrame}=load('lib/stdWuxiaEffects.ts');
const effect={type:'impact_shake',asset_id:'state',duration_seconds:.24,intensity:.45,center:[.7,.5],radius:.1,voice_binding:{exact_anchor:'hit'}};
const scene={effects:[effect]},state={asset_id:'state',face_exclusion_boxes:[[.1,.1,.2,.3]]},range=()=>({start:10.2,end:10.6});
test('short deterministic impact is synchronized to scene/voice time and stops outside the event',()=>{const at=t=>wuxiaEffectFrame(scene,state,[],t,10,12,range);assert.equal(at(10).scale,1);assert.notEqual(at(10.3).dx,0);assert.deepEqual(at(10.3),at(10.3));assert.equal(at(10.5).dx,0);assert.equal(at(10.5).scale,1)});
test('state cut stops the effect and shifted faces cannot collide with lettering or frame edge',()=>{assert.equal(wuxiaEffectFrame(scene,{...state,asset_id:'other'},[],10.3,10,12,range).dx,0);const bad={...state,face_exclusion_boxes:[[0,0,.2,.3]]};assert.match(wuxiaEffectFrame(scene,bad,[],10.3,10,12,range).issues[0],/unsafe_shake/);const graphics=[{layout:{center:[.15,.2],size:[.1,.2]}}];assert.match(wuxiaEffectFrame(scene,state,graphics,10.3,10,12,range).issues[0],/unsafe_shake/)});
test('debris and flashes avoid reviewed heads and text; malformed or unbound effects are explicit errors',()=>{const s={effects:[{...effect,type:'debris_burst'}]},f=wuxiaEffectFrame(s,state,[],10.3,10,12,range);assert.ok(f.overlays.length);assert.equal(wuxiaEffectFrame(s,{...state,face_exclusion_boxes:[[0,0,1,1]]},[],10.3,10,12,range).overlays.length,0);assert.match(wuxiaEffectFrame(scene,state,[],10.3,10,12,()=>null).issues[0],/unmatched/);assert.match(wuxiaEffectFrame({effects:[{...effect,type:'unknown'}]},state,[],10.3,10,12,range).issues[0],/invalid/)});
test('precise camera face review belongs to the actual active source SHA',()=>{const e={...effect,source_sha256:'sha',camera_face_boxes:[[.1,.1,.2,.3]]},sc={effects:[e]};assert.deepEqual(wuxiaEffectFrame(sc,{...state,sha256:'sha'},[],10.3,10,12,range).issues,[]);assert.match(wuxiaEffectFrame(sc,{...state,sha256:'changed'},[],10.3,10,12,range).issues[0],/invalid_camera/);assert.deepEqual(wuxiaEffectFrame(sc,{...state,asset_id:'other',sha256:'other'},[],10.3,10,12,range).issues,[])});
test('a small cart bump uses its bounded authored amplitude and silent scene clock',()=>{const e={...effect,amplitude_px:1.5,voice_binding:undefined,preview_at:.1};const f=wuxiaEffectFrame({effects:[e]},state,[],.5,0,4,()=>null);assert.ok(Math.abs(f.dx)<=1.5);assert.ok(f.scale<=1.004);assert.match(wuxiaEffectFrame({effects:[{...e,amplitude_px:100}]},state,[],.5,0,4,()=>null).issues[0],/invalid_amplitude/)});
test('ten fast full shakes retain all direction reversals at render fps and leave the other axis fixed',()=>{
 for(const axis of ['vertical','horizontal']){
  const e={...effect,duration_seconds:1,shake_cycles:10,shake_axis:axis,amplitude_px:axis==='vertical'?12:16,voice_binding:undefined};
  const frames=Array.from({length:24},(_,i)=>wuxiaEffectFrame({effects:[e]},state,[],i/24,0,2,()=>null,24));
  assert.ok(frames.every(f=>!f.issues.length));const values=frames.map(f=>axis==='vertical'?f.dy:f.dx).filter(x=>x!==0);
  const signs=values.map(Math.sign).filter((x,i,a)=>!i||x!==a[i-1]);assert.equal(signs.length,20);
  assert.ok(frames.every(f=>axis==='vertical'?f.dx===0:f.dy===0));
  assert.equal(wuxiaEffectFrame({effects:[e]},state,[],1,0,2,()=>null,24).scale,1);
 }
});
test('an unsampleable ten-cycle burst fails explicitly instead of silently becoming one shake',()=>{
 const e={...effect,duration_seconds:.3,shake_cycles:10,shake_axis:'vertical'};
 assert.match(wuxiaEffectFrame({effects:[e]},state,[],.1,0,2,()=>null,24).issues[0],/invalid_shake_repeat/);
});

test('10 Hz keeps its rate for 1, 3 and 5 seconds, including pause/seek and both axes',()=>{
 for(const duration of [1,3,5])for(const axis of ['vertical','horizontal']){
  const e={...effect,duration_seconds:duration,shake_hz:10,shake_axis:axis,amplitude_px:8,voice_binding:undefined};
  const at=t=>wuxiaEffectFrame({effects:[e]},state,[],t,0,8,()=>null,24);
  const frames=Array.from({length:duration*24},(_,i)=>at(i/24));
  assert.ok(frames.every(f=>!f.issues.length));
  const signs=frames.map(f=>Math.sign(axis==='vertical'?f.dy:f.dx)).filter(Boolean).filter((v,i,a)=>!i||v!==a[i-1]);
  assert.equal(signs.length,duration*20);assert.deepEqual(at(.625),at(.625));
  assert.equal(at(duration).scale,1);assert.equal(at(duration+.5).dx,0);
  assert.ok(frames.every(f=>axis==='vertical'?f.dx===0:f.dy===0));
 }
});
test('fixed rate rejects undersampling, ambiguous cycle/rate settings and oversized durations',()=>{
 const e={...effect,duration_seconds:5,shake_hz:10,shake_axis:'vertical'};
 for(const [patch,fps]of [[{},19],[{shake_hz:8},24],[{shake_cycles:10},24],[{duration_seconds:11},24]]){
  assert.ok(wuxiaEffectFrame({effects:[{...e,...patch}]},state,[],.2,0,12,()=>null,fps).issues.length);
 }
});
