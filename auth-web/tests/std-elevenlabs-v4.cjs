const fs = require('node:fs'), assert = require('node:assert/strict'), ts = require('typescript');
const route = fs.readFileSync('auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts', 'utf8');
const ast = ts.createSourceFile('route.ts', route, ts.ScriptTarget.Latest, true);
const names = ['shouldRotateElevenLabsKey','isElevenLabsVoiceAccessError','parseElevenLabsQuotaError','shouldRetryElevenLabsWithAlternateModel','buildElevenLabsModelCandidates','generateSingleElevenLabsChunk'];
const source = ast.statements.filter(s => ts.isFunctionDeclaration(s) && names.includes(s.name?.text)).map(s=>s.getText(ast)).join('\n');
const code = ts.transpile(source+'\nreturn generateSingleElevenLabsChunk;', {target:9,module:1});
const calls = [];
let reject = false;
const synthesize = new Function('fetch','Buffer','DEFAULT_ELEVENLABS_MODEL_ID','FALLBACK_ELEVENLABS_MODEL_IDS',code)(async (_, request) => {
  calls.push(JSON.parse(request.body));
  if (reject) return {ok:false,status:422,text:async()=> 'model unsupported'};
  return {ok:true,headers:new Headers({'content-type':'audio/mpeg'}),arrayBuffer:async()=>new Uint8Array(512).buffer};
},Buffer,'eleven_multilingual_v2',['eleven_v3','eleven_multilingual_v2']);
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
  console.log('PASS: v4 API model, explicit failure without model downgrade, distinct v2/v4 audio caches');
})().catch(e=>{console.error(e);process.exitCode=1});
