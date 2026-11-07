const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),load=require('./load-ts-module.cjs');
const {isWuxiaMovingtoon,usesStandardSubtitles,wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts');
test('wuxia disables captions while preserving speech data and other categories',()=>{
 const project={project_payload:{structure:{image_style:'wuxia_webtoon'},render_settings:{subtitles_enabled:true},subtitles:[{text:'spoken'}]}};
 assert.equal(isWuxiaMovingtoon(project),true);assert.equal(usesStandardSubtitles(project),false);assert.equal(project.project_payload.subtitles.length,1);
 assert.equal(usesStandardSubtitles({project_payload:{structure:{image_style:'jidaigeki_cel'}}}),true);
 assert.equal(usesStandardSubtitles({project_payload:{render_settings:{subtitles_enabled:false}}}),false);
});
test('only authored state graphics appear at the current scene time',()=>{
 const p={structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'E01_S01',states:[{asset_id:'a',start:0,end:.5},{asset_id:'b',start:.5,end:1}],graphics:[{text:'actual dialogue',state_asset_id:'b',preview_start:.7,preview_end:.95}]}]}}};const rows=[{scene_number:1,start_num:10,end_num:30,text:'entire narration'}];
 assert.deepEqual(wuxiaSceneFrame(p,1,rows,11).graphics,[]);const frame=wuxiaSceneFrame(p,1,rows,26);assert.equal(frame.state.asset_id,'b');assert.equal(frame.graphics[0].text,'actual dialogue');assert.equal(wuxiaSceneFrame(p,2,rows,26),null);
});
const {wuxiaBubbleContour}=load('lib/stdWuxiaBubble.ts');
test('unified closed contour has a short tail and clearance before its anchor',()=>{
 const b=wuxiaBubbleContour([100,100],[160,80],[180,300]);
 assert.equal((b.path.match(/M /g)||[]).length,1);assert.ok(b.path.endsWith(' Z'));
 assert.ok(b.tailLength<=54);assert.ok(Math.hypot(180-b.tip[0],300-b.tip[1])>=64);
 assert.equal(wuxiaBubbleContour([100,100],[160,80],[100,100]).tip,null);
 assert.equal(wuxiaBubbleContour([100,100],[160,80],[100,155]).tip,null);
});
test('silent visual scenes retain authored cut timing without invented speech rows',()=>{
 const scene={scene_id:'E04_S08',preview_start_seconds:30,preview_duration_seconds:4,states:[{asset_id:'a',start:0,end:.5},{asset_id:'b',start:.5,end:1}],graphics:[],effects:[]};
 const p={project_payload:{structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[scene]}}}};
 assert.equal(wuxiaSceneFrame(p,8,[],30.5).state.asset_id,'a');assert.equal(wuxiaSceneFrame(p,8,[],32.1).state.asset_id,'b');assert.equal(wuxiaSceneFrame(p,8,[],32.1).timingBasis,'authored_silent_scene_clock');
});
