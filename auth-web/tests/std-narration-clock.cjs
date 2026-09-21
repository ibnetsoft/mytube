const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict'),test=require('node:test');
function load(path){const e={};new Function('exports',ts.transpile(fs.readFileSync(path,'utf8'),{module:1,target:7}))(e);return e}
const mp3=load('auth-web/lib/stdJoinMp3.ts');
const preview=load('auth-web/lib/stdPreviewAudio.ts');
function frame(){const b=Buffer.alloc(417);b.set([255,251,144,0]);return b}
test('timeline measures encoded frames without stretching audio',()=>{const b=Buffer.concat(Array.from({length:100},frame));assert(Math.abs(mp3.mp3FrameDuration(b)-100*1152/44100)<1e-9);assert.throws(()=>mp3.mp3FrameDuration(b.subarray(0,b.length-1)),/Truncated/)});
test('saved audio uses actual boundaries instead of scheduled five seconds',()=>{const subs=[{text:'첫 구간',voice_id:'v',start_num:0,end_num:2},{text:'둘째 구간',voice_id:'v',start_num:2,end_num:5}];const timeline=[{text:'첫 구간',voice_id:'v',start:0,end:4},{text:'둘째 구간',voice_id:'v',start:4,end:9}];const out=preview.alignedNarrationSubtitles(subs,timeline);assert.equal(out[1].start_num,4);assert.equal(out[1].end_num,9);assert.equal(subs[1].start_num,2);assert.equal(preview.alignedNarrationSubtitles([{...subs[0],text:'수정됨'},subs[1]],timeline),null);assert.equal(preview.alignedNarrationSubtitles(subs,[]),null)});
