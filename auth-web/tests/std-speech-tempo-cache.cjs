const fs=require('fs'),assert=require('node:assert/strict'),ts=require('typescript');
const code=ts.transpile(fs.readFileSync('auth-web/lib/stdSegmentAudioCache.ts','utf8'),{module:1,target:9});const e={};new Function('require','exports',code)(id=>id==='crypto'?require(id):id==='./stdVoicePerformance'?{voicePerformanceKey:()=>''}: {},e);
const identity={text:'문장',voiceId:'v',modelId:'eleven_v4',speed:1.1,stability:0.7,style:0.45,direction:'',tempoProcessing:'atempo-v1'};
const old={text:identity.text,voice_id:'v',model_id:'eleven_v4',tts_speed:1.1,stability:0.7,style:0.45,direction:''};
assert.equal(e.legacySegmentMatches(old,identity),false);assert.equal(e.legacySegmentMatches({...old,tempo_processing:'atempo-v1'},identity),true);console.log('PASS: unprocessed speed-labelled clips are not reused');
