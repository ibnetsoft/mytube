const test=require('node:test'),assert=require('node:assert/strict');
const load=require('./load-ts-module.cjs'),lib=load('lib/stdSubtitleNarration.ts');
test('explicit narration and dialogue override contradictory AI coloring',()=>{
 const parts=[{text:'働いて返す約束で、客の代金ではない。',dialogue:true,speaker:'お澄'}];
 assert.equal(lib.subtitleDialogueDisplayParts({text:parts[0].text,dialogue_override:false},parts,false,'')[0].dialogue,false);
 assert.equal(lib.subtitleDialogueDisplayParts({text:'manual',dialogue_override:true},[{text:'manual',dialogue:false}],true,'お澄')[0].dialogue,true);
 assert.deepEqual(lib.subtitleDialogueDisplayParts({text:parts[0].text},parts,true,'お澄'),parts);
});
test('scene 66 line 4 switches to the same scene narrator without changing text, timing or other rows',()=>{
 const rows=[{scene_number:66,text:'narration',voice_id:'Sulafat',voice_name:'Sulafat',voice_direction:'calm'},
  {id:'scene66-4',scene_number:66,text:'働いて返す約束で、客の代金ではない。',voice_id:'Yukari',dialogue_override:false,dialogue_kind:'dialogue',editor_speaker:{name:'お澄'},dialogue_speaker:'お澄',start_num:860,end_num:864,audio_url:'old.wav'},
  {scene_number:77,voice_id:'Other',text:'other'}];
 const original=structuredClone(rows),updated=lib.assignSubtitleNarration(rows,1,'default',new Map(),(_,index)=>index!==1);
 assert.equal(updated[1].voice_id,'Sulafat');assert.equal(updated[1].dialogue_override,false);assert.equal(updated[1].dialogue_kind,'narration');assert.equal(updated[1].editor_speaker,null);assert.equal(updated[1].dialogue_speaker,null);
 for(const key of ['text','id','scene_number','start_num','end_num','audio_url'])assert.equal(updated[1][key],original[1][key]);
 assert.strictEqual(updated[0],rows[0]);assert.strictEqual(updated[2],rows[2]);assert.deepEqual(rows,original);
});
test('a different scene or character voice cannot become the narration donor',()=>{
 const rows=[{scene_number:1,voice_id:'wrong'}, {scene_number:2,voice_id:'actor'}, {scene_number:2,text:'target',voice_id:'actor'}];
 const updated=lib.assignSubtitleNarration(rows,2,'default',new Map([['default','Narrator']]),(_,index)=>index===0);
 assert.equal(updated[2].voice_id,'default');assert.equal(updated[2].voice_name,'Narrator');assert.equal(updated[2].voice_direction,'');
});
