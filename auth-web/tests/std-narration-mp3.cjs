const assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),os=require('os'),cp=require('child_process'),ts=require('../node_modules/typescript');
const req=require('module').createRequire(path.resolve(__dirname,'../package.json')),cache={};
function load(file){if(cache[file])return cache[file];const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:1,target:9,esModuleInterop:true}}).outputText)(ex,n=>n.startsWith('.')?load(path.resolve(path.dirname(file),n+'.ts')):req(n));return cache[file]=ex}
const {finalizeNarrationMp3}=load(path.resolve(__dirname,'../lib/stdNarrationMp3.ts'));
const {joinMp3Segments,mp3FrameDuration}=load(path.resolve(__dirname,'../lib/stdJoinMp3.ts'));
const {narrationDurationMatchesTimeline}=load(path.resolve(__dirname,'../lib/stdPreviewAudio.ts'));
const ffmpeg=req('ffmpeg-static');
(async()=>{const dir=fs.mkdtempSync(path.join(os.tmpdir(),'air-mp3-test-'));try{
const clips=[44100,24000,44100].map((rate,i)=>{const file=path.join(dir,i+'.mp3');cp.execFileSync(ffmpeg,['-v','error','-f','lavfi','-i',`sine=frequency=${440+i*220}:duration=0.6:sample_rate=${rate}`,'-ac',i===2?'2':'1','-b:a',rate===24000?'64k':'128k',file]);return fs.readFileSync(file)});
const result=await finalizeNarrationMp3(clips),total=result.durations.reduce((a,b)=>a+b,0),frames=joinMp3Segments([result.audioBuffer]);
assert.ok(Math.abs(mp3FrameDuration(frames)-total)<0.00001);
assert.ok(result.audioBuffer.includes(Buffer.from('Info'))||result.audioBuffer.includes(Buffer.from('Xing')),'final join must contain a duration/seek header');
const file=path.join(dir,'final.mp3');fs.writeFileSync(file,result.audioBuffer);
const pcm=cp.execFileSync(ffmpeg,['-v','error','-i',file,'-f','s16le','-ar','44100','-ac','1','pipe:1']);
assert.ok(Math.abs(pcm.length/2/44100-total)<0.04,'decoded duration must match the subtitle timeline');
assert.equal(result.durations.length,3);
assert.equal(narrationDurationMatchesTimeline(2048.647625,[{end_num:2053.383}]),false,'reported production duration mismatch');
assert.equal(narrationDurationMatchesTimeline(total,[{end_num:total}]),true);
assert.equal(narrationDurationMatchesTimeline(NaN,[{end_num:total}]),false);
await assert.rejects(finalizeNarrationMp3([Buffer.from('invalid audio')]),/MP3/);
console.log('PASS: mixed sample rates/channels, final MP3 seek header, actual decoded duration, invalid inputs and legacy playback fallback');
}finally{fs.rmSync(dir,{recursive:true,force:true})}})().catch(e=>{console.error(e);process.exit(1)});
