const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), ts = require('../node_modules/typescript');
const lib = {};
new Function('exports', 'require', ts.transpile(fs.readFileSync('lib/stdLipSync.ts', 'utf8'), {module:1,target:7}))(lib, require);
function fixture() {
 const subtitles = [{text:'설명', voice_id:'n',scene_number:1,start:0,end:1,dialogue_kind:'narration'},
  {text:'어머니',voice_id:'a',scene_number:1,start:1,end:2,dialogue_kind:'dialogue',dialogue_speaker:'소녀'},
  {text:'끝',voice_id:'n',scene_number:3,start:4,end:5,dialogue_kind:'narration'}];
 const project = {project_payload:{subtitles,lipsync:{enabled:true}}}, scenes=[1,2,3].map(n=>({scene_number:n}));
 const assets=[{id:'audio',asset_type:'audio',status:'assigned',metadata:{subtitle_timeline:subtitles.map(s=>({...s}))}},
  {id:'image',asset_type:'image',status:'assigned',scene_number:1,metadata:{gcs_path:'image.png'}}];
 return {project,scenes,assets};
}
test('only dialogue is scheduled; visual-only boundaries interpolate recorded times',()=>{
 const f=fixture(),plan=lib.lipSyncPlan(f.project,f.scenes,f.assets);
 assert.equal(plan.length,1);assert.deepEqual(plan[0].shots.map(s=>s.text),['어머니']);
 assert.deepEqual(lib.lipSyncSceneStarts(f.project,f.scenes,f.assets[0]),[0,2,4]);
 assert.equal(plan[0].end,2);
 f.assets[0].metadata.subtitle_timeline[1].end=3.5;
 assert.deepEqual(lib.lipSyncSceneStarts(f.project,f.scenes,f.assets[0]),[0,3.5,4]);
});
test('edited text, voice, missing and non-finite timings require TTS confirmation',()=>{
 for(const patch of [{text:'수정'},{voice_id:'different'},{start:NaN}]){
  const f=fixture();Object.assign(f.project.project_payload.subtitles[1],patch);
  assert.throws(()=>lib.lipSyncPlan(f.project,f.scenes,f.assets));
 }
});
test('render requires current reviewed lip sync AND AE, and audio replacement invalidates results',()=>{
 const f=fixture(),p=lib.lipSyncPlan(f.project,f.scenes,f.assets)[0];
 const a={id:'ae',asset_type:'video',status:'assigned',metadata:{lipsync_fingerprint:p.fingerprint,lipsync_reviewed:true,ae_reviewed:false,timing_locked:true}};
 f.assets.push(a);assert.throws(()=>lib.reviewedLipSyncAssets(f.project,f.scenes,f.assets));
 a.metadata.ae_reviewed=true;assert.equal(lib.reviewedLipSyncAssets(f.project,f.scenes,f.assets).get(1).id,'ae');
 f.assets[0].id='new-audio';assert.throws(()=>lib.reviewedLipSyncAssets(f.project,f.scenes,f.assets));
});
test('existing projects without lip sync keep their render path',()=>{
 assert.equal(lib.reviewedLipSyncAssets({project_payload:{}},[],[]).size,0);
});
test('saved editor start_num/end_num times are accepted',()=>{
 const f=fixture();f.project.project_payload.subtitles.forEach(s=>{s.start_num=s.start;s.end_num=s.end;delete s.start;delete s.end});
 assert.equal(lib.lipSyncPlan(f.project,f.scenes,f.assets).length,1);
});

test('visual-only scenes never take time away from continuous speech',()=>{
 const f=fixture();f.project.project_payload.subtitles[2].start=2;
 f.assets[0].metadata.subtitle_timeline[2].start=2;
 assert.deepEqual(lib.lipSyncSceneStarts(f.project,f.scenes,f.assets[0]),[0,2,2]);
 assert.equal(lib.lipSyncPlan(f.project,f.scenes,f.assets)[0].end,2);
});
