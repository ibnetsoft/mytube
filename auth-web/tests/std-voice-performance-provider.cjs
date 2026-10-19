const fs=require('fs'),assert=require('node:assert/strict'),ts=require('typescript');
const helpers=require('../../scripts/std_web_runtime.cjs').load('stdVoicePerformance');
const raw=fs.readFileSync('auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts','utf8');
const ast=ts.createSourceFile('route.ts',raw,ts.ScriptTarget.Latest,true);
const names=['splitText','cleanTtsText','buildElevenLabsModelCandidates','shouldRotateElevenLabsKey','isElevenLabsVoiceAccessError','parseElevenLabsQuotaError','shouldRetryElevenLabsWithAlternateModel','generateSingleElevenLabsChunk','generateElevenLabsMp3'];
const functions=ast.statements.filter(s=>ts.isFunctionDeclaration(s)&&names.includes(s.name?.text)).map(s=>s.getText(ast)).join('\n');
const calls=[];
const context={...helpers,Buffer,MAX_CHARS_PER_REQUEST:4500,DEFAULT_ELEVENLABS_MODEL_ID:'eleven_v4',DEFAULT_ELEVENLABS_VOICE_ID:'Laura',FALLBACK_ELEVENLABS_MODEL_IDS:['eleven_v3','eleven_multilingual_v2'],
    isVoiceStudioVoice:()=>false,mergeVoiceStudioSegments:s=>s,
    fetch:async(url,init)=>{calls.push(JSON.parse(init.body));return new Response(Buffer.alloc(512),{headers:{'content-type':'audio/mpeg'}})}};
const code=ts.transpile(functions+'\nreturn generateElevenLabsMp3;',{target:9,module:1});
const generate=new Function(...Object.keys(context),code)(...Object.values(context));
(async()=>{
    const text='조용히. 이제 신나게!';
    const performance=helpers.normalizeVoicePerformance({version:1,text,cues:[{offset:0,tag:'whispers'},{offset:5,tag:'excited'}]},text);
    const input={apiKeys:['fixture'],voiceId:'Laura',modelId:'eleven_v4',text,speed:1,style:0.45,stability:0.5,performance};
    await generate(input);
    assert.equal(calls[0].text,'[whispers] 조용히. [excited] 이제 신나게!');
    assert.equal(calls[0].model_id,'eleven_v4');assert.deepEqual(calls[0].voice_settings,{stability:0.5});
    await generate({...input,performance:undefined,voiceSegments:[{text,voiceId:'Laura',performance}]});
    assert.equal(calls[1].text,calls[0].text,'Subtitle-segment generation passes the same validated tags');
    await generate({...input,modelId:'eleven_multilingual_v2'});
    assert.equal(calls[2].text,text,'Older models receive only plain speech');
    assert.equal(calls[2].voice_settings.style,0.45);
    console.log('PASS: actual provider request contains mid-line vocal tags only for v4 and omits unsupported v4 settings');
})().catch(e=>{console.error(e);process.exitCode=1});
