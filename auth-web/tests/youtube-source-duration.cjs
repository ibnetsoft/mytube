const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');const lib={};
new Function('exports',ts.transpile(fs.readFileSync('lib/youtubeSourceDuration.ts','utf8'),{module:1,target:7}))(lib);
assert.equal(lib.youtubeDurationSeconds('PT16M47S'),1007);assert.equal(lib.youtubeDurationSeconds('PT1H'),3600);
assert.throws(()=>lib.youtubeDurationSeconds('PT0S'));assert.throws(()=>lib.youtubeDurationSeconds('PT2H'));assert.throws(()=>lib.youtubeVideoId('https://evil.example/abcdefghijk'));
(async()=>{let calls=0;const result=await lib.fetchYoutubeSourceDuration('https://youtu.be/abcdefghijk',['fixture-key'],async url=>{calls++;assert.equal(url.hostname,'www.googleapis.com');assert.equal(url.searchParams.get('part'),'contentDetails,snippet');return {ok:true,json:async()=>({items:[{id:'abcdefghijk',contentDetails:{duration:'PT16M47S'},snippet:{liveBroadcastContent:'none'}}]})}});
assert.equal(result.source_duration_seconds,1007);assert.equal(calls,1);
await assert.rejects(()=>lib.fetchYoutubeSourceDuration('https://youtu.be/abcdefghijk',[],async()=>{throw Error('must not fetch')}));
await assert.rejects(()=>lib.fetchYoutubeSourceDuration('https://youtu.be/abcdefghijk',['fixture'],async()=>({ok:true,json:async()=>({items:[]})})));
console.log('PASS: actual source runtime, invalid/unavailable/live-length rejection and fixed metadata endpoint');})().catch(e=>{console.error(e);process.exitCode=1});
