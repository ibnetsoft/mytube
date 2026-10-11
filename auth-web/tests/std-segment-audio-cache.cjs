const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
function load(file,deps={}){const exports={};new Function('require','exports',ts.transpile(fs.readFileSync(file,'utf8'),{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}))((id)=>id in deps?deps[id]:require(id),exports);return exports}
const gcs={isGcsConfiguredAsync:async()=>true,uploadGcsBuffer:async({objectPath,buffer})=>{if(failUpload)throw Error('GCS upload failed');stored.set(objectPath,buffer);uploads++;return {bucket:'air-studio-prod',path:objectPath}},downloadGcsObject:async({objectPath})=>{if(failDownload)throw Error('offline');return stored.get(objectPath)}};
const helper=load('auth-web/lib/stdSegmentAudioCache.ts',{'@/lib/gcsStorage':gcs});
const batches=load('auth-web/lib/stdNarrationBatch.ts');
const mp3=load('auth-web/lib/stdJoinMp3.ts');
const stored=new Map(); let failDownload=false; const claims=new Set();const assets=[];let generated=0,uploads=0,failUpload=false,providerHook=null;const removedClaims=[];
const project={id:'10b3d223-1457-415a-ba40-7b947c6c1b3d',language:'ko'};
const db={storage:{from:()=>({
    remove:async(paths)=>{for(const path of paths){removedClaims.push(path);claims.delete(path);stored.delete(path)}return {error:null}},
    download:async(path)=>{
        const buffer=stored.get(path);
        return {data:failDownload||!buffer?null:{arrayBuffer:async()=>buffer,text:async()=>buffer.toString('utf8')},
            error:failDownload?{message:'offline'}:!buffer?{message:'not found',statusCode:'404'}:null};
    },
    upload:async(path,buffer,options)=>{
        if(path.includes('/claims/')){
            if(claims.has(path)&&!options?.upsert)return {error:{message:'exists',statusCode:'409'}};
            claims.add(path);stored.set(path,Buffer.from(buffer));return {error:null};
        }
        stored.set(path,buffer);uploads++;return {error:failUpload?{message:'offline'}:null};
    }
})},from(table){let filters=[],inserted;const q={select(){return q},eq(k,v){filters.push([k,v]);return q},in(k,v){if(k==='metadata->>cache_key')filters.push([k,v]);return q},neq(){return q},update(){return q},then(resolve){return Promise.resolve({data:table==='std_project_assets'?assets.filter(a=>filters.every(([k,v])=>(Array.isArray(v)?v.includes(k.startsWith('metadata->>')?a.metadata[k.slice(11)]:a[k]):(k.startsWith('metadata->>')?a.metadata[k.slice(11)]:a[k])===v))):[],error:null}).then(resolve)},order(){return q},limit(){return q},insert(v){inserted=v;return q},async single(){const a={...inserted,id:String(assets.length+1)};assets.push(a);return {data:a}},async maybeSingle(){return {data:table==='std_projects'?project:assets.find(a=>filters.every(([k,v])=>(Array.isArray(v)?v.includes(k.startsWith('metadata->>')?a.metadata[k.slice(11)]:a[k]):(k.startsWith('metadata->>')?a.metadata[k.slice(11)]:a[k])===v)))||null}}};return q}};
function route(){return load('auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts',{
    '@/lib/stdRecordedSubtitleTiming':load('auth-web/lib/stdRecordedSubtitleTiming.ts'),
    '@/lib/gcsStorage':gcs,'@/lib/stdNarrationBatch':batches,
    'next/server':{NextResponse:{json:(data,options)=>({data,status:options?.status||200,ok:!options?.status||options.status<400,json:async()=>data})}},
    '@/lib/stdStoredNarration':load('auth-web/lib/stdStoredNarration.ts',{'./stdNarrationMp3':{finalizeNarrationMp3:async clips=>({audioBuffer:mp3.joinMp3Segments(clips),durations:clips.map(mp3.mp3FrameDuration)})}}),'@/lib/stdSegmentAudioCache':helper,'@/lib/supabaseAdmin':{supabaseAdmin:db},
    '@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:'test@example.com',user:{id:'test'}}})},
    '@/lib/stdGoogleDrive':{driveFileLink:()=>'',ensureStdProjectDriveFolders:()=>{throw Error('Must not use Drive')}},
    '@/lib/stdVoiceStudio':{generateVoiceStudioMp3:async(input)=>{generated++;if(providerHook)await providerHook(input);const frame=Buffer.alloc(417);frame.set([0xff,0xfb,0x90,0x00]);return frame}},
    '@/lib/voiceStudioCatalog':{isVoiceStudioVoice:v=>v!=='eleven-test-voice',mergeVoiceStudioSegments:s=>s},
    '@/lib/stdTtsCompletion':{completedScriptTtsProgress:p=>p},'@/lib/stdLegacySync':{},'@/lib/stdMultiVoice':{},'@/lib/elevenLabsKeys':{getConfiguredElevenLabsKeys:async()=>[]}
})}
const body={text:'남았네.',voice_id:'Charon',provider:'voice_studio',mode:'vrew_segment_preview_fast',cache_key:'legacy-key',speed:1,stability:0.35,style:0.45,segment_index:2};
const call=(r,b=body)=>r.POST({json:async()=>b},{params:{projectId:project.id}});
(async()=>{
 const missingPreview=await call(route(),{...body,cache_only:true,volume:80,volume_ratio:0.8});
 assert.equal(missingPreview.status,404);assert.equal(missingPreview.data.code,'audio_not_cached');
 assert.equal(generated,0,'Previewing an uncached subtitle must never call a TTS provider');
 assert.equal(claims.size,0,'A read-only preview miss must not claim audio generation');
 assert.equal(uploads,0);assert.equal(stored.size,0);assert.equal(assets.length,0,'A read-only preview miss must not persist audio or asset metadata');
 let first=await call(route());assert.equal(first.status,200);assert.equal(first.data.persistence_pending,false);assert.equal(generated,1);assert.equal(uploads,1);assert.match(first.data.audio_url,/assets\/file\?assetId=/);
 assert.equal(first.data.cached,false,'An explicit generation request after a preview miss must still generate and save the missing clip');
 const existingClaims=[...claims],existingStored=[...stored.keys()],existingUploads=uploads,existingAssets=assets.length;
 for(const volume of [80,0,200]){
   const adjusted=await call(route(),{...body,cache_only:true,volume,volume_ratio:volume/100});
   assert.equal(adjusted.status,200);assert.equal(adjusted.data.cached,true);
   assert.equal(adjusted.data.asset.id,first.data.asset.id,'Volume is a playback gain and must reuse the same recording');
 }
 assert.equal(generated,1,'Reducing, muting, or amplifying volume must not synthesize another recording');
 assert.equal(uploads,existingUploads);assert.equal(assets.length,existingAssets);assert.deepEqual([...claims],existingClaims);assert.deepEqual([...stored.keys()],existingStored);
 console.log('PASS: uncached read-only preview spends no credits or storage writes; explicit generation remains available; volume-only previews reuse the saved clip');
 let second=await call(route());assert.equal(second.data.cached,true);assert.equal(generated,1,'A fresh server instance must reuse persisted audio');
 let moved=await call(route(),{...body,segment_index:9,cache_key:'changed-index'});assert.equal(moved.data.cached,true);assert.equal(generated,1);
 await call(route(),{...body,text:'남았습니다.'});assert.equal(generated,2,'Changed Korean text must generate a different cache entry');
 await call(route(),{...body,voice_id:'Other'});assert.equal(generated,3);
 failUpload=true;let failed=await call(route(),{...body,text:'저장 실패 검사'});assert.equal(failed.status,500);assert.equal(assets.length,3,'Failed save must not be reported as persisted');
 failUpload=false; const full=await call(route(),{...body,mode:'full'});assert.equal(full.status,200);assert.equal(full.data.asset.asset_type,'audio');assert.equal(full.data.asset.metadata.storage_bucket,'air-studio-prod');assert.match(full.data.persisted_audio_url,/assets\/file/);assert.equal(full.data.drive_file,null);
 const page=fs.readFileSync('auth-web/app/std/page.tsx','utf8');assert(!page.includes('prefetchVrewSegment(selectedSubIndex)'));assert(!page.includes('requestSegmentAudio(true)'));assert(!page.includes('persistVrewSegmentAudio'));
 const bypass=await call(route(),{...body,bypass_cache:true});assert.equal(bypass.data.cached,true);
 const parallelBody={...body,text:'동시 요청 테스트'};const prior=generated;const parallel=await Promise.all([call(route(),parallelBody),call(route(),parallelBody)]);assert.equal(generated,prior+1);assert(parallel.some(r=>r.status===200));assert(parallel.some(r=>r.status===409||r.data.cached));
 assets.push({id:'legacy-moved',project_id:project.id,asset_type:'other',drive_file_id:'legacy-drive',metadata:{kind:'vrew_segment_tts',cache_key:'obsolete-index',text:'이전 음성',voice_id:body.voice_id,model_id:'eleven_multilingual_v2',tts_speed:1,stability:0.35,style:0.45}});const beforeLegacy=generated;const legacy=await call(route(),{...body,text:'이전 음성',segment_index:150});assert.equal(legacy.data.cached,false);assert.notEqual(legacy.data.asset.id,'legacy-moved');assert.equal(generated,beforeLegacy+1,'Drive-only legacy cache must be regenerated into storage-backed audio');
 const before=generated;const retry=await call(route(),{...body,text:'저장 실패 검사'});assert.equal(retry.status,409);assert.equal(generated,before);
 const fullBody={...body,mode:'full',voice_segments:[{text:body.text,voice_id:body.voice_id},{text:'새로운 조각',voice_id:body.voice_id}]};
 const start=generated;const assembled=await call(route(),fullBody);assert.equal(assembled.status,200);assert.equal(generated,start+1);assert.deepEqual(assembled.data.segment_reuse,{reused:1,generated:1});
 const again=await call(route(),fullBody);assert.equal(again.status,200);assert.equal(generated,start+1);assert.deepEqual(again.data.segment_reuse,{reused:2,generated:0});
 const changed=await call(route(),{...fullBody,voice_segments:[fullBody.voice_segments[0],{text:'새로운 조각 수정',voice_id:body.voice_id}]});assert.equal(changed.status,200);assert.equal(generated,start+2);assert.deepEqual(changed.data.segment_reuse,{reused:1,generated:1});
 const voiceChanged=await call(route(),{...fullBody,voice_segments:[fullBody.voice_segments[0],{text:'새로운 조각',voice_id:'Changed'}]});assert.equal(voiceChanged.status,200);assert.equal(generated,start+3);
 const settingStart=generated; const settings=await call(route(),{...fullBody,speed:0.9,voice_segments:[fullBody.voice_segments[0]]});assert.equal(settings.status,200);assert.equal(generated,settingStart+1);
 const checkpoint=generated;failDownload=true;const unreadable=await call(route(),{...fullBody,voice_segments:[{text:'must not generate',voice_id:body.voice_id},fullBody.voice_segments[0]]});assert.equal(unreadable.status,500);assert.equal(generated,checkpoint);failDownload=false;
 assert(page.includes('if (useSubtitleVoiceSegments ||'), 'Full assembly errors must not fall back to paid browser synthesis');
 const batchedBody={...fullBody,voice_segments:Array.from({length:9},(_,i)=>({text:'분할 음성 '+i,voice_id:body.voice_id}))};
 const audioBefore=assets.filter(a=>a.asset_type==='audio').length;const genBefore=generated;const ready=[];
 const batched=await batches.generateNarrationInBatches(batchedBody,async b=>{const r=await call(route(),b);if(b.mode==='prepare_narration_segments')assert.equal(assets.filter(a=>a.asset_type==='audio').length,audioBefore);return {res:r,payload:r.data}},n=>ready.push(n));
 assert.equal(batched.res.status,200);assert.deepEqual(ready,[4,8,9]);assert.equal(generated,genBefore+9);
 assert.equal(assets.filter(a=>a.asset_type==='audio').length,audioBefore+1);
 const cachedAgain=await batches.generateNarrationInBatches(batchedBody,async b=>{const r=await call(route(),b);return {res:r,payload:r.data}},()=>{});
 assert.equal(cachedAgain.res.status,200);assert.equal(generated,genBefore+9);assert.equal(cachedAgain.payload.segment_reuse.generated,0);
 const missingFinal=await call(route(),{...batchedBody,mode:'assemble_narration_segments',voice_segments:[{text:'not prepared',voice_id:body.voice_id}]});
 assert.equal(missingFinal.status,500);assert.equal(generated,genBefore+9,'Final join cannot synthesize missing audio');
 const oversized=await call(route(),{...batchedBody,mode:'prepare_narration_segments'});assert.equal(oversized.status,400);

 // A returned Google error proves no audio was delivered; only that provider's
 // owned claim may be released. Unknown outcomes keep the duplicate-spend guard.
 const cloudRejection=()=>Object.assign(new Error('Google Cloud TTS HTTP 500: INTERNAL'),{name:'VoiceStudioCloudError',noAudioProduced:true});
 const captureNewClaim=previous=>{
   const claimPath=[...claims].find(path=>!previous.has(path));
   assert(claimPath,'Provider must run after an audio generation claim is acquired');
   const claim=JSON.parse(stored.get(claimPath).toString('utf8'));
   assert.equal(typeof claim.request_id,'string');assert(claim.request_id.length>0);assert(Number.isFinite(Date.parse(claim.requested_at)));
   return {claimPath,claim};
 };
 const definiteBody={...body,text:'Google definite rejection can be retried'};
 const definiteClaims=new Set(claims);const definiteStart=generated;let definiteClaim;
 providerHook=async()=>{definiteClaim=captureNewClaim(definiteClaims);throw cloudRejection()};
 const definiteFailure=await call(route(),definiteBody);providerHook=null;
 assert.equal(definiteFailure.status,500);assert.equal(generated,definiteStart+1);
 assert(!claims.has(definiteClaim.claimPath),'A definite provider rejection must release its own claim');
 assert(!stored.has(definiteClaim.claimPath),'The claim JSON must be removed from storage');
 const definiteRetry=await call(route(),definiteBody);
 assert.equal(definiteRetry.status,200,'Immediate manual retry must not wait for claim expiration');assert.equal(generated,definiteStart+2);
 assert.equal((await call(route(),definiteBody)).data.cached,true);assert.equal(generated,definiteStart+2,'A successful manual retry is persistently reusable');

 const uncertainBody={...body,text:'Unknown provider timeout must remain claimed'};
 const uncertainClaims=new Set(claims);const uncertainStart=generated;let uncertainClaim;
 providerHook=async()=>{uncertainClaim=captureNewClaim(uncertainClaims);throw Object.assign(new Error('Provider request timed out'),{name:'AbortError'})};
 assert.equal((await call(route(),uncertainBody)).status,500);providerHook=null;
 assert(claims.has(uncertainClaim.claimPath));assert(stored.has(uncertainClaim.claimPath));
 assert.equal((await call(route(),uncertainBody)).status,409);assert.equal(generated,uncertainStart+1,'Unknown provider outcomes must not trigger a second paid request');

 const foreignBody={...body,text:'A replaced worker claim must survive rejection'};
 const foreignClaims=new Set(claims);const foreignStart=generated;let foreignClaim;
 providerHook=async()=>{
   foreignClaim=captureNewClaim(foreignClaims);
   stored.set(foreignClaim.claimPath,Buffer.from(JSON.stringify({...foreignClaim.claim,request_id:'other-worker-request'})));
   throw cloudRejection();
 };
 assert.equal((await call(route(),foreignBody)).status,500);providerHook=null;
 assert(claims.has(foreignClaim.claimPath),'A rejected older request must preserve a newer worker claim');
 assert.equal(JSON.parse(stored.get(foreignClaim.claimPath).toString()).request_id,'other-worker-request');
 assert(!removedClaims.includes(foreignClaim.claimPath),'Ownership mismatch must never issue a storage delete');
 assert.equal((await call(route(),foreignBody)).status,409);assert.equal(generated,foreignStart+1);

 const rejectionBatch={...body,mode:'prepare_narration_segments',segment_offset:40,
   voice_segments:['Successful before rejection','Failed subtitle in batch','Successful after rejection'].map(text=>({text,voice_id:body.voice_id}))};
 const rejectionStart=generated;const rejectionAudioBefore=assets.filter(a=>a.asset_type==='audio').length;
 providerHook=async input=>{if(input.text==='Failed subtitle in batch')throw cloudRejection()};
 const failedBatch=await call(route(),rejectionBatch);providerHook=null;
 assert.equal(failedBatch.status,500);assert.match(failedBatch.data.error,/42/,'Batch error must identify the global 1-based subtitle: offset 40 + index 1 + 1');
 assert.equal(failedBatch.data.provider,'voice_studio');assert.equal(failedBatch.data.model_id,'gemini-2.5-flash-tts');
 const readyPeers=assets.filter(a=>['Successful before rejection','Successful after rejection'].includes(a.metadata?.text));
 assert.equal(readyPeers.length,2,'Successful concurrent clips remain saved when another subtitle fails');
 assert.equal(assets.filter(a=>a.asset_type==='audio').length,rejectionAudioBefore,'A failed prepare batch must not publish a final narration');
 const afterRejectedBatch=generated;assert.equal(afterRejectedBatch,rejectionStart+3);
 const recoveredBatch=await call(route(),rejectionBatch);
 assert.equal(recoveredBatch.status,200);assert.equal(generated,afterRejectedBatch+1,'Manual retry generates only the rejected subtitle');
 assert.deepEqual(recoveredBatch.data.segment_reuse,{reused:2,generated:1});
 const successfulBatchAgain=await call(route(),rejectionBatch);
 assert.equal(successfulBatchAgain.status,200);assert.equal(generated,afterRejectedBatch+1);assert.deepEqual(successfulBatchAgain.data.segment_reuse,{reused:3,generated:0});
 const mixedFailure=await call(route(),{...rejectionBatch,voice_segments:[{text:'Missing ElevenLabs key in a Google-led batch',voice_id:'eleven-test-voice'}]});
 assert.equal(mixedFailure.status,500);assert.match(mixedFailure.data.error,/ElevenLabs API key/);
 assert.equal(mixedFailure.data.provider,'elevenlabs','Early failures without provider metadata inherit the failed subtitle provider, not the overall Google batch');
 assert.equal(mixedFailure.data.model_id,'eleven_multilingual_v2');
 const originalFetch=global.fetch;const originalLanguage=project.language;let googleCalls=0;
 try {
   project.language='ja';
   global.fetch=async url=>{
     const request=new URL(url);assert.equal(request.hostname,'translate.google.com');assert.equal(request.searchParams.get('tl'),'ja');
     googleCalls++;
     const frame=Buffer.alloc(417);frame.set([0xff,0xfb,0x90,0x00]);
     return new Response(frame,{headers:{'Content-Type':'audio/mpeg'}});
   };
   const googleBody={...body,text:'伏せろ！',voice_id:'google_kr',provider:'google_free',cache_only:false};
   const firstGoogle=await call(route(),googleBody);
   assert.equal(firstGoogle.status,200);assert.equal(firstGoogle.data.cached,false);assert.match(firstGoogle.data.audio_url,/assets\/file\?assetId=/);
   assert.equal(googleCalls,1,'A missing Google preview generates one recording');
   const savedGoogle=await call(route(),{...googleBody,cache_only:true});
   assert.equal(savedGoogle.status,200);assert.equal(savedGoogle.data.cached,true);
   assert.equal(savedGoogle.data.asset.id,firstGoogle.data.asset.id);
   assert.equal(googleCalls,1,'The next preview uses the saved Google recording');
 } finally {global.fetch=originalFetch;project.language=originalLanguage}
 console.log('PASS: a missing Google free preview generates and persists one Japanese clip, then reuses it');
 console.log('PASS: definite Google rejection releases only its owned claim; timeout/failed storage retain duplicate-spend protection; batch errors identify the global subtitle and preserve successful clips');
 console.log('PASS: full narration reuses preview clips; unchanged repeat makes zero provider calls; text/voice change generates only one; unreadable cache fails before spending');
 console.log('PASS: cache bypass ignored; uncertain failure cannot spend credits again; persistent reuse across reload, Drive-only legacy regeneration, Korean/voice invalidation, save failure, no selection auto-generation');
})().catch(e=>{console.error(e);process.exit(1)});
