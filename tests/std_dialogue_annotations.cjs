const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('../auth-web/node_modules/typescript');
const source = fs.readFileSync(require('node:path').join(__dirname, '../auth-web/lib/stdDialogueAnnotations.ts'), 'utf8');
const obj = {}; new Function('exports', ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText)(obj);
const map = obj.mapDialogueAnnotations;
const text = '문서에 적혀 있었다. “어서 와.” 그가 말했다.';
const start = Array.from(text.slice(0,text.indexOf('어서'))).length;
const annotations = {version:1,source:'codex-ai',scenes:[{scene_number:1,source_text:text,spans:[{start,end:start+5,text:'어서 와.',speaker:'아버지',status:'confirmed'}]}]};
const subs = [{scene_number:1,text:'문서에 적혀 있었다. 어서'}, {scene_number:1,text:'와. 그가 말했다.'}];
let result = map(subs,annotations);
assert.equal(result.size,2);
assert.equal([...result.values()].flat().filter(p=>p.dialogue).map(p=>p.text).join(''),'어서와.');
assert.equal(map([{scene_number:1,text:'다른 대본'}],annotations).size,0);
assert.equal(map(subs,null).size,0);
annotations.scenes[0].spans[0].status='uncertain';
assert.equal([...map(subs,annotations).values()].flat().some(p=>p.dialogue),false);
console.log('AI dialogue subtitle mapping passed');

annotations.scenes[0].spans[0].status='confirmed';
const original = [{id:'a', scene_number:1, text: '문서에 적혀 있었다. 어서 와. 그가 말했다.', start_time:'10',end_time:'20',image_url:'scene.png',voice_id:'narrator',audio_url:'old.mp3'}];
const split = obj.splitSubtitleDialogueBlocks(original,annotations);
assert.equal(split.length,3);
assert.equal(split.map(s=>s.text).join(''),original[0].text);
assert.deepEqual(split.map(s=>s.dialogue_kind),['narration','dialogue','narration']);
assert.equal(split[0].start_num,10); assert.equal(split[2].end_num,20);
assert.equal(split[0].end_num,split[1].start_num);
assert.ok(split.every(s=>s.scene_number===1 && s.image_url==='scene.png' && !s.audio_url));
assert.deepEqual(obj.splitSubtitleDialogueBlocks(split,annotations),split);
assert.deepEqual(obj.splitSubtitleDialogueBlocks(original,null),original);
const two = '어서 와.반갑다.';
const twoAnnotations = {version:1,source:'codex-ai',scenes:[{scene_number:1,source_text:two,spans:[
 {text:'어서 와.',start:0,end:5,speaker:'가',status:'confirmed'},
 {text:'반갑다.',start:5,end:9,speaker:'나',status:'confirmed'}]}]};
assert.deepEqual(obj.splitSubtitleDialogueBlocks([{...original[0],text:two}],twoAnnotations).map(s=>s.dialogue_speaker),['가','나']);
console.log('AI speech-boundary splitting, speakers, timing and idempotency passed');
