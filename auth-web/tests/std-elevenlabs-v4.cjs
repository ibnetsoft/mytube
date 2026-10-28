const fs = require('node:fs'), assert = require('node:assert/strict'), ts = require('typescript');
const route = fs.readFileSync('auth-web/lib/stdTtsGenerate.ts', 'utf8');
const ast = ts.createSourceFile('route.ts', route, ts.ScriptTarget.Latest, true);
const names = ['shouldRotateElevenLabsKey','isElevenLabsVoiceAccessError','parseElevenLabsQuotaError','shouldRetryElevenLabsWithAlternateModel','buildElevenLabsModelCandidates','generateSingleElevenLabsChunk'];
const source = ast.statements.filter(s => ts.isFunctionDeclaration(s) && names.includes(s.name?.text)).map(s=>s.getText(ast)).join('\n');
const code = ts.transpile(source+'\nreturn generateSingleElevenLabsChunk;', {target:9,module:1});
const calls = [];
let reject = false;
const synthesize = new Function('fetch','Buffer','DEFAULT_ELEVENLABS_MODEL_ID','FALLBACK_ELEVENLABS_MODEL_IDS','elevenLabsVoiceSettings',code)(async (_, request) => {
  calls.push(JSON.parse(request.body));
  if (reject) return {ok:false,status:422,text:async()=> 'model unsupported'};
  return {ok:true,headers:new Headers({'content-type':'audio/mpeg'}),arrayBuffer:async()=>new Uint8Array(512).buffer};
},Buffer,'eleven_multilingual_v2',['eleven_v3','eleven_multilingual_v2'],require('../../scripts/std_web_runtime.cjs').load('stdVoicePerformance').elevenLabsVoiceSettings);
(async()=>{
  const input = {apiKeys:['fixture'],voiceId:'Laura',modelId:'eleven_v4',chunk:'同じ声です。',speed:1,stability:0.7,style:0.45};
  const result = await synthesize(input);
  assert.equal(result.modelId,'eleven_v4');
  assert.equal(calls[0].model_id,'eleven_v4');
  reject = true; calls.length = 0;
  await assert.rejects(synthesize(input),/422/);
  assert.deepEqual(calls.map(c=>c.model_id),['eleven_v4'],'Do not synthesize older audio under a v4 cache identity');
  const runtime = require('../../scripts/std_web_runtime.cjs');
  const {segmentAudioKey,legacySegmentMatches} = runtime.load('stdSegmentAudioCache');
  const identity = {text:'같은 대본',voiceId:'Laura',modelId:'eleven_multilingual_v2',speed:1,stability:0.7,style:0.45,direction:''};
  const v4 = {...identity,modelId:'eleven_v4'};
  assert.notEqual(segmentAudioKey(identity),segmentAudioKey(v4));
  assert.equal(legacySegmentMatches({text:identity.text,voice_id:'Laura',model_id:identity.modelId,tts_speed:1,stability:0.7,style:0.45,direction:''},v4),false);
  const oldRecording = {text:identity.text,voice_id:'Laura',provider:'elevenlabs',model_id:identity.modelId,tts_speed:1,stability:0.7,style:0.45,direction:''};
  assert.equal(legacySegmentMatches(oldRecording,v4,true),true,'Default upgrade must reuse unchanged old recordings');
  assert.equal(legacySegmentMatches(oldRecording,{...v4,text:'새 대본'},true),false,'Changed text must generate new audio');
  assert.equal(legacySegmentMatches(oldRecording,{...v4,voiceId:'Different'},true),false);
  assert.equal(oldRecording.model_id,'eleven_multilingual_v2','Never relabel saved recordings');
  assert.match(route,/const DEFAULT_ELEVENLABS_MODEL_ID = 'eleven_v4'/);
  for (const file of ['auth-web/app/std/page.tsx','auth-web/lib/stdTtsGenerate.ts']) {
    const text = fs.readFileSync(file,'utf8');
    const declaration = text.match(/const cacheModelForVoice = .*$/m)[0];
    for (const chosen of ['eleven_multilingual_v2','eleven_v4']) {
      const pick = new Function('isVoiceStudioVoice','DEFAULT_ELEVENLABS_MODEL_ID','modelId','elevenLabsModel',ts.transpile(declaration+';return cacheModelForVoice;',{target:9,module:1}))(
        id=>id.startsWith('gemini:'),'eleven_multilingual_v2',chosen,chosen);
      assert.equal(pick('Laura'),chosen);
      assert.equal(pick('gemini:Charon'),'eleven_multilingual_v2','ElevenLabs selection must preserve reusable Google narration');
      assert.equal(pick('google_kr'),'eleven_multilingual_v2');
    }
  }
  console.log('PASS: v4 API model, explicit failure without model downgrade, distinct v2/v4 audio caches');
})().catch(e=>{console.error(e);process.exitCode=1});
