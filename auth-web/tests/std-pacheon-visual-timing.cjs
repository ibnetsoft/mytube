const test=require('node:test'),assert=require('node:assert/strict');
const {lipSyncSceneStarts,lipSyncPlan}=require('./load-ts-module.cjs')('lib/stdLipSync.ts');
test('requested Pacheon visual timing preserves recorded speech',()=>{
 const boundary=2.5861224489795918, subtitles=[{text:'첫 대사',voice_id:'a',scene_number:1,start:0,end:boundary,dialogue_kind:'narration'},{text:'다음 대사',voice_id:'b',scene_number:5,start:boundary,end:4.388571428571431,dialogue_kind:'dialogue'}];
 const project={id:'1fdf20be-170f-4536-a329-fba1f5607b9d',project_payload:{subtitles,lipsync:{enabled:false}}},scenes=[1,2,3,4,5].map(scene_number=>({scene_number}));
 const audio={id:'audio',asset_type:'audio',status:'assigned',metadata:{subtitle_timeline:subtitles.map(s=>({...s}))}}, starts=lipSyncSceneStarts(project,scenes,audio);
 assert(Math.abs(starts[1]-(boundary-1.05))<1e-9);
 for(let i=1;i<4;i++)assert(Math.abs(starts[i+1]-starts[i]-.7)<1e-9);
 assert(Math.abs(starts[4]-(boundary+1.05))<1e-9);
 assert.equal(audio.metadata.subtitle_timeline[1].start,boundary);
 assert.doesNotThrow(()=>lipSyncPlan(project,scenes,[audio]));
});
