const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts');
test('dialogue follows its timed voice row and selects its authored image even if the provisional fraction differs',()=>{
 const p={structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'E01_S01',states:[{asset_id:'a',start:0,end:.8},{asset_id:'b',start:.8,end:1}],graphics:[{kind:'speech_bubble',text:'짐꾼. 내려놔.',state_asset_id:'b',preview_start:.82,preview_end:.95}]}]}}};
 const rows=[{scene_number:1,text:'내레이션',start_num:0,end_num:5},{scene_number:1,text:'짐꾼, 내려놔!',start_num:5,end_num:7},{scene_number:1,text:'다음',start_num:7,end_num:20}];
 assert.equal(wuxiaSceneFrame(p,1,rows,4).graphics.length,0);
 assert.equal(wuxiaSceneFrame(p,1,rows,6).state.asset_id,'b');
 assert.equal(wuxiaSceneFrame(p,1,rows,6).graphics.length,1);
 assert.equal(wuxiaSceneFrame(p,1,rows,8).graphics.length,0);
});
