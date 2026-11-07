const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {validWuxiaMouth,wuxiaMouthFrame,hasWuxiaMouths}=load('lib/stdWuxiaMouth.ts');
const {wuxiaSceneFrame}=load('lib/stdWuxiaPresentation.ts');
const {freezeWuxiaScene,wuxiaStateSource}=load('lib/stdWuxiaNative.ts');
function fixture(){
 const row={id:'r1',scene_number:1,text:'말해.',start_num:10,end_num:12,voice_id:'voice',dialogue_kind:'dialogue',dialogue_speaker:'서진'};
 const pose=i=>({media_url:`/api/std/frame-${i}`,sha256:String(i).repeat(64),gcs_bucket:'test',gcs_path:`${i}.png`});
 const mouth={id:'mouth',contract:'wuxia_dialogue_mouth/v1',enabled:true,speaker:'seojin',block_ids:['quote'],source_sha256:'a'.repeat(64),audio_asset_id:'audio',audio_sha256:'b'.repeat(64),width:1920,height:1080,face_box:[.1,.1,.4,.5],mouth_box:[.2,.3,.3,.4],review:{mouth_fully_visible:true,face_large_enough:true,occluded:false,identity_preserved:true},bindings:[{id:'r1',text:'말해.',start:10,end:12,voice_id:'voice',dialogue_speaker:'서진'}],cues:[{at_seconds:10,pose:'closed'},{at_seconds:10.1,pose:'open'},{at_seconds:10.3,pose:'half'},{at_seconds:11,pose:'closed'}],poses:{closed:pose(1),half:pose(2),open:pose(3)}};
 const state={asset_id:'state',sha256:mouth.source_sha256,start:0,end:1,media_url:'/api/std/assets/gcs-file?bucket=test&path=state.png',dialogue_mouths:[mouth]};
 const graph={block_id:'quote',kind:'speech_bubble',speaker:'seojin',text:'말해.',state_asset_id:'state',preview_start:0,preview_end:1,layout:{center:[.7,.1],size:[.2,.1]}};
 const project={project_payload:{subtitle_source_audio_id:'audio',structure:{wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'S001',states:[state],graphics:[graph]}]}}}};
 return {mouth,state,graph,row,project};
}
test('only sufficiently large and actually visible mouths qualify; zero selected is valid',()=>{
 const {mouth,project}=fixture();assert.ok(validWuxiaMouth(mouth));assert.equal(validWuxiaMouth({...mouth,face_box:[.1,.25,.4,.4]}),false);assert.equal(validWuxiaMouth({...mouth,review:{...mouth.review,occluded:true}}),false);assert.equal(hasWuxiaMouths(project),true);assert.deepEqual(wuxiaMouthFrame({},[],project,[],11),[]);
});
test('recorded speech drives pose; pause and reverse seek are deterministic',()=>{
 const {project,row}=fixture(),at=t=>wuxiaSceneFrame(project,1,[row],t);assert.equal(at(10.1).mouths[0].pose,'open');assert.equal(at(10.3).mouths[0].pose,'half');assert.equal(at(11).mouths[0].pose,'closed');assert.equal(at(10.1).mouths[0].pose,'open');assert.equal(at(12).mouths.length,0);assert.deepEqual(at(10.3).mouths,at(10.3).mouths);
});
test('narration, another speaker, stale voice/timing and source changes never animate',()=>{
 const f=fixture(),at=(state,graphs,project,rows)=>wuxiaMouthFrame(state,graphs,project,rows,10.2);
 assert.deepEqual(at(f.state,[{...f.graph,speaker:'other'}],f.project,[f.row]),[]);assert.deepEqual(at(f.state,[f.graph],f.project,[{...f.row,dialogue_kind:'narration'}]),[]);assert.deepEqual(at(f.state,[f.graph],f.project,[{...f.row,start_num:10.01}]),[]);assert.deepEqual(at({...f.state,sha256:'c'.repeat(64)},[f.graph],f.project,[f.row]),[]);assert.deepEqual(at(f.state,[f.graph],{project_payload:{...f.project.project_payload,subtitle_source_audio_id:'new'}},[f.row]),[]);
});
test('AE frozen samples and authored state source keep the same exact mouth poses',()=>{
 const {project,row}=fixture();const source=wuxiaStateSource(project,1);assert.equal(source.metadata.gcs_path,'state.png');const frozen=freezeWuxiaScene(project,1,[row],10,12,24,source);assert.equal(frozen.states[0].dialogue_mouths.length,1);assert.equal(frozen.samples[3].mouths[0].pose,'open');assert.throws(()=>freezeWuxiaScene(project,1,[{...row,text:'바뀐 말'}],10,12,24,source));
});
