const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
const page=fs.readFileSync('auth-web/app/std/page.tsx','utf8');const from=page.indexOf('    const setSubtitleBlockVoice =');const to=page.indexOf('    const subtitleVoiceSegments',from);assert(from>0&&to>from);
const subtitles=Array.from({length:9},(_,i)=>({id:'line-'+i,text:'text '+i,voice_id:i===2?'george':i>=5&&i<=7?'sarah':'gemini:Charon',dialogue_override:i===2||i>=5&&i<=7}));
let saved,stale=[];
const compiled=ts.transpile(page.slice(from,to)+'\nreturn setSubtitleBlockVoice;',{target:7,module:1});
const update=new Function('selectedVoice','localSubtitles','currentNav','isPlayingPreview','stopVrewPlayback','voiceNameById','markVrewSegmentStale','persistVrewVoiceSubtitles',compiled)('gemini:Charon',subtitles,'subtitle_vrew',false,()=>{},new Map([['eleven-new','New voice']]),(item,index)=>stale.push(index),async rows=>saved=rows);
(async()=>{await update(8,'eleven-new');assert.equal(saved[8].voice_id,'eleven-new');assert.deepEqual(stale,[8]);for(let i=0;i<8;i++)assert.equal(saved[i],subtitles[i]);assert.equal(saved[8].dialogue_override,false);console.log('PASS: ninth subtitle changes alone; dialogue/narration classification and other eight voices remain unchanged')})().catch(e=>{console.error(e);process.exitCode=1});
