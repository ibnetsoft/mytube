const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
function load(file){const exports={};new Function('exports',ts.transpile(fs.readFileSync(file,'utf8'),{module:1,target:7}))(exports);return exports}
const {subtitleSpeaker,assignSpeakerVoice}=load('auth-web/lib/stdSpeakerAssignment.ts');
const {mapDialogueAnnotations}=load('auth-web/lib/stdDialogueAnnotations.ts');
const text='옥례 아이는 죽었다면서. 그런데 이 아이는 누구냐.';
const rows=[{scene_number:20,text:'옥례 아이는 죽었다면서. 그런데 이',voice_id:'sarah'}, {scene_number:20,text:'아이는 누구냐.',voice_id:'sarah'}, {scene_number:21,text:'순임은 대답했습니다.',voice_id:'gemini:Charon'}, {scene_number:22,text:'저도 알고 있어요.',voice_id:'sarah'}];
const annotations={version:1,source:'codex-ai',scenes:[{scene_number:20,source_text:text,spans:[{start:0,end:Array.from(text).length,text,speaker:'덕수',status:'confirmed'}]}]};
const parts=mapDialogueAnnotations(rows,annotations),cast=[{name:'덕수',gender:'male'}];
let speakers=rows.map((r,i)=>subtitleSpeaker(r,parts.get(i),cast));
assert.equal(speakers[0].name,'덕수');assert.equal(speakers[1].gender,'male');assert.equal(speakers[2],null);
const updated=assignSpeakerVoice(rows,0,'george','George',true,speakers);
assert.deepEqual(updated.map(r=>r.voice_id),['george','george','gemini:Charon','sarah']);assert.deepEqual(updated.map(r=>r.text),rows.map(r=>r.text));assert.equal(updated[2],rows[2]);
assert.equal(assignSpeakerVoice(rows,0,'george','George',false,speakers)[1],rows[1]);
const manual={...rows[0],editor_speaker:{name:'덕수',gender:'male',text:rows[0].text}};
assert.equal(subtitleSpeaker(manual,undefined,[]).name,'덕수');assert.equal(subtitleSpeaker({...manual,text:'수정된 문장'},undefined,[]),null);
assert.equal(subtitleSpeaker(rows[0],[{dialogue:true,text:'A',speaker:'덕수'},{dialogue:true,text:'B',speaker:'순임'}],cast),null);
// Execute the actual TTS segment builder: editorial attribution never reaches speech.
const page=fs.readFileSync('auth-web/app/std/page.tsx','utf8');
const source=page.slice(page.indexOf('    const subtitleVoiceSegments ='),page.indexOf('    const vrewSegmentCacheKey ='));
const segments=new Function('localSubtitles','selectedVoice',ts.transpile(source+'; return subtitleVoiceSegments()', {target:7}))([manual, ...updated.slice(1)],'gemini:Charon');
assert.equal(segments[0].text,rows[0].text);assert(!JSON.stringify(segments).includes('덕수'));assert(!JSON.stringify(segments).includes('editor_speaker'));
console.log('PASS: confirmed attribution, same-character scope, stale/ambiguous attribution, original subtitles and actual TTS input exclude speaker metadata');
