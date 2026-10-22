const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const lib=require('./load-ts-module.cjs')(path.resolve(__dirname,'../lib/stdSubtitleSpeakerProgress.ts'));
test('manual narration leaves missing-speaker list and TTS speaker count despite AI dialogue',()=>{
 const rows=[{text:'scene 66',dialogue_override:false},{text:'scene 77',dialogue_override:false},{text:'real dialogue'}];
 const parts=new Map(rows.map((row,index)=>[index,[{text:row.text,dialogue:true}]]));
 assert.deepEqual(lib.missingSpeakerSubtitleIndexes(rows,parts,[null,null,null]),[2]);
 assert.deepEqual(lib.subtitleSpeakerProgress(rows,parts,[null,null,null]),{total:1,confirmed:0});
 assert.deepEqual(lib.missingSpeakerSubtitleIndexes(rows,parts,[null,null,{name:'Speaker'}]),[]);
 assert.deepEqual(lib.subtitleSpeakerProgress(rows,parts,[null,null,{name:'Speaker'}]),{total:1,confirmed:1});
});
test('all explicitly narrated rows satisfy the speaker gate; reverting restores AI classification',()=>{
 const parts=new Map([[0,[{dialogue:true}]]]);
 const rows=[{text:'narration',dialogue_override:false,dialogue_speaker:'stale',editor_speaker:{name:'stale'}}];
 assert.deepEqual(lib.missingSpeakerSubtitleIndexes(rows,parts,[null]),[]);
 assert.deepEqual(lib.subtitleSpeakerProgress(rows,parts,[null]),{total:0,confirmed:0});
 assert.deepEqual(lib.missingSpeakerSubtitleIndexes([{text:'automatic'}],parts,[null]),[0]);
});
