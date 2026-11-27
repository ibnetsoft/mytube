const test=require('node:test'),assert=require('node:assert/strict');
const {lipSyncSceneStarts,lipSyncPlan}=require('./load-ts-module.cjs')('lib/stdLipSync.ts');
test('explicit scene starts preserve recorded speech and individual silent scene durations',()=>{
 const subtitles=[{text:'첫 대사',voice_id:'a',scene_number:1,start:0,end:2.5,dialogue_kind:'narration'},{text:'다음 대사',voice_id:'b',scene_number:5,start:6.1,end:8,dialogue_kind:'dialogue'}];
 const project={id:'1fdf20be-170f-4536-a329-fba1f5607b9d',project_payload:{subtitles,lipsync:{enabled:false}}},scenes=[1,2,3,4,5].map(scene_number=>({scene_number}));
 const audio={id:'audio',asset_type:'audio',status:'assigned',metadata:{subtitle_timeline:subtitles.map(s=>({...s})),scene_timing_starts:[0,2.5,3.7,4.7,6.1]}};
 assert.deepEqual(lipSyncSceneStarts(project,scenes,audio),audio.metadata.scene_timing_starts);
 assert.doesNotThrow(()=>lipSyncPlan(project,scenes,[audio]));
 audio.metadata.scene_timing_starts=[0,1,3.7,4.7,6.1];
 assert.throws(()=>lipSyncSceneStarts(project,scenes,audio),/확정 음성/);
});
