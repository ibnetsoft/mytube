const {test}=require('node:test'),assert=require('node:assert/strict');
const load=require('./load-ts-module.cjs');
const {ambientFrameIndex,validAmbientLoop,freezeAmbientLoops}=load('lib/stdAmbientLoop.ts');
const {wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts');
const frame=(n,d)=>({media_url:`/api/std/frames/${n}`,sha256:String(n).repeat(64),duration_ms:d,gcs_bucket:'test',gcs_path:`frame-${n}.png`});
const loop={contract:'ambient_loop/v1',enabled:true,width:1920,height:1080,source_sha256:'a'.repeat(64),role:'background',region:[0,0,.2,.2],protected_regions:[[.4,.3,.7,.8]],start_ms:100,end_ms:1000,phase_ms:0,repeat:true,frames:[frame(1,100),frame(2,200),frame(3,50)]};
test('variable durations, exact boundaries, repeat, phase and once',()=>{
 assert.ok(validAmbientLoop(loop));
 assert.deepEqual([99,100,199,200,399,400,449,450,999,1000].map(t=>ambientFrameIndex(loop,t)),[null,0,0,1,1,2,2,0,1,null]);
 assert.equal(ambientFrameIndex({...loop,repeat:false},900),2);
 assert.equal(ambientFrameIndex({...loop,phase_ms:100},100),1);
 assert.equal(ambientFrameIndex({...loop,enabled:false},200),null);
});
test('protected faces and changed original are rejected',()=>{
 assert.equal(validAmbientLoop({...loop,region:[0,0,.8,.8]}),false);
 assert.equal(validAmbientLoop({...loop,protected_regions:[[.1,.1,.3,.3]]}),false);
 assert.throws(()=>freezeAmbientLoops({project_payload:{}},1,{metadata:{sha256:'b'.repeat(64),ambient_loops:[loop]}}));
});
test('editor seek/pause/cut uses scene clock, not elapsed playback',()=>{
 const state={asset_id:'one',sha256:loop.source_sha256,start:0,end:.5,image_url:'original.png',ambient_loops:[loop]};
 const project={structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'S001',states:[state,{asset_id:'two',start:.5,end:1,image_url:'next.png'}],graphics:[]}]}}};
 const rows=[{scene_number:1,start_num:10,end_num:12,text:'말'}];
 const at=t=>wuxiaSceneFrame(project,1,rows,t);
 assert.equal(at(10.2).ambient[0].index,1);assert.equal(at(10.4).ambient[0].index,2);
 assert.equal(at(10.2).ambient[0].index,1);assert.deepEqual(at(10.2),at(10.2));
 assert.equal(at(11.1).ambient.length,0);assert.equal(at(10).ambient.length,0);
});
test('native submission freezes all state cuts and the same editable bubble contour',()=>{
 const {freezeWuxiaScene}=load('lib/stdWuxiaNative.ts');
 const a={asset_id:'a',sha256:loop.source_sha256,start:0,end:.5,media_url:'/api/std/assets/gcs-file?bucket=test&path=a.png',ambient_loops:[loop]};
 const b={asset_id:'b',sha256:'b'.repeat(64),start:.5,end:1,media_url:'/api/std/assets/gcs-file?bucket=test&path=b.png'};
 const g={block_id:'quote',kind:'speech_bubble',state_asset_id:'a',text:'대사',preview_start:0,preview_end:.5,layout:{center:[.7,.1],size:[.2,.1]},style:{size:38}};
 const project={project_payload:{structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'S001',states:[a,b],graphics:[g]}]}}}};
 const rows=[{scene_number:1,start_num:10,end_num:12,text:'설명'}];
 const result=freezeWuxiaScene(project,1,rows,10,12,24,{metadata:{sha256:a.sha256}});
 assert.equal(result.samples.length,48);assert.equal(result.samples[23].state,'a');assert.equal(result.samples[24].state,'b');
 assert.equal(result.states[1].gcs_path,'b.png');assert.equal(result.samples[23].graphics.length,1);assert.equal(result.samples[24].graphics.length,0);
 assert.ok(result.graphics['0'].points.length>100);assert.equal(result.graphics['0'].text,'대사');
});
test('sword energy keeps the same patch clock and rejects unbound protection metadata',()=>{
 const sword_aura={contract:'wuxia_sword_aura/v1',source_reviewed:true,source_sha256:loop.source_sha256,clean_plate_sha256:'c'.repeat(64),reason:'visible blue sword energy',amplitude_px:5,protected_polygons:[[[.4,.3],[.7,.3],[.7,.8]]]};
 const a={...loop,sword_aura};assert.equal(validAmbientLoop(a),true);assert.equal(ambientFrameIndex(a,200),1);
 assert.equal(validAmbientLoop({...a,sword_aura:{...sword_aura,source_sha256:'b'.repeat(64)}}),false);
 assert.equal(validAmbientLoop({...a,sword_aura:{...sword_aura,protected_polygons:[[[2,0],[1,0],[0,1]]]}}),false);
});
test('reviewed attack PNG sequence retains exact half-open contact clock and source identity',()=>{
 const sprite={...loop,start_ms:833,end_ms:1333,repeat:false,attack_sprite:{contract:'wuxia_attack_sprite/v1',source_sha256:loop.source_sha256,source_reviewed:true,frames_reviewed:true,event:'charged blade contacts stone',reason:'reviewed PNG key drawings',contact_ms:750,protected_boxes:[[.4,.3,.7,.8]]}}
 assert(validAmbientLoop(sprite));assert.equal(ambientFrameIndex(sprite,832),null);assert.equal(ambientFrameIndex(sprite,833),0);assert.equal(ambientFrameIndex(sprite,1333),null)
 assert(!validAmbientLoop({...sprite,repeat:true}));assert(!validAmbientLoop({...sprite,attack_sprite:{...sprite.attack_sprite,source_sha256:'b'.repeat(64)}}))
})
