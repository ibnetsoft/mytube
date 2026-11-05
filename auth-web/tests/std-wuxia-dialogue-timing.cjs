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
const {correctedWuxiaPackage}=load('lib/stdWuxiaPresentation.ts');
test('first scene correction applies only to the inspected original layout and preserves artist edits',()=>{
 const state={asset_id:'s',sha256:'18feb83a4b3cd8873870adc0e13baffc75f3693afeeb568951074593915977dc'};
 const graphic={kind:'speech_bubble',text:'짐꾼. 거기 서 있지 말고 내려놔.',state_asset_id:'s',layout:{center:[.29,.19],size:[.34,.23],tail:[.2,.43]}};
 const pkg={scenes:[{states:[state],graphics:[graphic]}]};const corrected=correctedWuxiaPackage(pkg);
 assert.deepEqual(corrected.scenes[0].graphics[0].layout.center,[.49,.14]);assert.deepEqual(graphic.layout.center,[.29,.19]);
 const edited={scenes:[{states:[state],graphics:[{...graphic,layout:{...graphic.layout,center:[.6,.2]}}]}]};assert.deepEqual(correctedWuxiaPackage(edited),edited);
});
test('a derived acting state retains its parent dialogue bubble',()=>{
 const p={structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'E01_S01',states:[{asset_id:'a',start:0,end:.5},{asset_id:'b',start:.5,end:.75},{asset_id:'b2',parent_asset_id:'b',start:.75,end:1}],graphics:[{kind:'speech_bubble',text:'대사',state_asset_id:'b',preview_start:.5,preview_end:1}]}]}}};
 const rows=[{scene_number:1,text:'대사',start_num:0,end_num:10}];
 const frame=wuxiaSceneFrame(p,1,rows,8);assert.equal(frame.state.asset_id,'b2');assert.equal(frame.graphics.length,1);
});
