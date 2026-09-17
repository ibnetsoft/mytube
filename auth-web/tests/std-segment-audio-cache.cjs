const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
function load(file,deps={}){const exports={};new Function('require','exports',ts.transpile(fs.readFileSync(file,'utf8'),{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}))((id)=>id in deps?deps[id]:require(id),exports);return exports}
const helper=load('auth-web/lib/stdSegmentAudioCache.ts');
const stored=new Map(); let failDownload=false; const claims=new Set();const assets=[];let generated=0,uploads=0,failUpload=false;
const project={id:'10b3d223-1457-415a-ba40-7b947c6c1b3d',language:'ko'};
const db={storage:{from:()=>({download:async(path)=>({data:failDownload?null:{arrayBuffer:async()=>stored.get(path)},error:failDownload?{message:"offline"}:null}),upload:async(path,buffer)=>{if(path.includes('/claims/')){if(claims.has(path))return {error:{message:'exists'}};claims.add(path);return {error:null}}stored.set(path,buffer);uploads++;return {error:failUpload?{message:'offline'}:null}}})},from(table){let filters=[],inserted;const q={select(){return q},eq(k,v){filters.push([k,v]);return q},in(){return q},neq(){return q},update(){return q},then(resolve){return Promise.resolve({data:table==='std_project_assets'?assets.filter(a=>filters.every(([k,v])=>(k.startsWith('metadata->>')?a.metadata[k.slice(11)]:a[k])===v)):[],error:null}).then(resolve)},order(){return q},limit(){return q},insert(v){inserted=v;return q},async single(){const a={...inserted,id:String(assets.length+1)};assets.push(a);return {data:a}},async maybeSingle(){return {data:table==='std_projects'?project:assets.find(a=>filters.every(([k,v])=>(k.startsWith('metadata->>')?a.metadata[k.slice(11)]:a[k])===v))||null}}};return q}};
function route(){return load('auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts',{
    'next/server':{NextResponse:{json:(data,options)=>({data,status:options?.status||200,ok:!options?.status||options.status<400,json:async()=>data})}},
    '@/lib/stdStoredNarration':load('auth-web/lib/stdStoredNarration.ts',{'./stdJoinMp3':load('auth-web/lib/stdJoinMp3.ts')}),'@/lib/stdSegmentAudioCache':helper,'@/lib/supabaseAdmin':{supabaseAdmin:db},
    '@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:'test@example.com',user:{id:'test'}}})},
    '@/lib/stdGoogleDrive':{driveFileLink:()=>'',ensureStdProjectDriveFolders:()=>{throw Error('Must not use Drive')}},
    '@/lib/stdVoiceStudio':{generateVoiceStudioMp3:async()=>{generated++;return Buffer.alloc(300)}},
    '@/lib/voiceStudioCatalog':{isVoiceStudioVoice:()=>true,mergeVoiceStudioSegments:s=>s},
    '@/lib/stdTtsCompletion':{completedScriptTtsProgress:p=>p},'@/lib/stdLegacySync':{},'@/lib/stdMultiVoice':{},'@/lib/elevenLabsKeys':{}
})}
const body={text:'남았네.',voice_id:'Charon',provider:'voice_studio',mode:'vrew_segment_preview_fast',cache_key:'legacy-key',speed:1,stability:0.35,style:0.45,segment_index:2};
const call=(r,b=body)=>r.POST({json:async()=>b},{params:{projectId:project.id}});
(async()=>{
 let first=await call(route());assert.equal(first.status,200);assert.equal(first.data.persistence_pending,false);assert.equal(generated,1);assert.equal(uploads,1);assert.match(first.data.audio_url,/assets\/file\?assetId=/);
 let second=await call(route());assert.equal(second.data.cached,true);assert.equal(generated,1,'A fresh server instance must reuse persisted audio');
 let moved=await call(route(),{...body,segment_index:9,cache_key:'changed-index'});assert.equal(moved.data.cached,true);assert.equal(generated,1);
 await call(route(),{...body,text:'남았습니다.'});assert.equal(generated,2,'Changed Korean text must generate a different cache entry');
 await call(route(),{...body,voice_id:'Other'});assert.equal(generated,3);
 failUpload=true;let failed=await call(route(),{...body,text:'저장 실패 검사'});assert.equal(failed.status,500);assert.equal(assets.length,3,'Failed save must not be reported as persisted');
 failUpload=false; const full=await call(route(),{...body,mode:'full'});assert.equal(full.status,200);assert.equal(full.data.asset.asset_type,'audio');assert.equal(full.data.asset.metadata.storage_bucket,'content-assets');assert.match(full.data.persisted_audio_url,/assets\/file/);assert.equal(full.data.drive_file,null);
 const page=fs.readFileSync('auth-web/app/std/page.tsx','utf8');assert(!page.includes('prefetchVrewSegment(selectedSubIndex)'));assert(!page.includes('requestSegmentAudio(true)'));assert(!page.includes('persistVrewSegmentAudio'));
 const bypass=await call(route(),{...body,bypass_cache:true});assert.equal(bypass.data.cached,true);
 const parallelBody={...body,text:'동시 요청 테스트'};const prior=generated;const parallel=await Promise.all([call(route(),parallelBody),call(route(),parallelBody)]);assert.equal(generated,prior+1);assert(parallel.some(r=>r.status===200));assert(parallel.some(r=>r.status===409||r.data.cached));
 assets.push({id:'legacy-moved',project_id:project.id,asset_type:'other',drive_file_id:'legacy-drive',metadata:{kind:'vrew_segment_tts',cache_key:'obsolete-index',text:'이전 음성',voice_id:body.voice_id,model_id:'eleven_multilingual_v2',tts_speed:1,stability:0.35,style:0.45}});const legacy=await call(route(),{...body,text:'이전 음성',segment_index:150});assert.equal(legacy.data.cached,true);assert.equal(legacy.data.asset.id,'legacy-moved');
 const before=generated;const retry=await call(route(),{...body,text:'저장 실패 검사'});assert.equal(retry.status,409);assert.equal(generated,before);
 const fullBody={...body,mode:'full',voice_segments:[{text:body.text,voice_id:body.voice_id},{text:'새로운 조각',voice_id:body.voice_id}]};
 const start=generated;const assembled=await call(route(),fullBody);assert.equal(assembled.status,200);assert.equal(generated,start+1);assert.deepEqual(assembled.data.segment_reuse,{reused:1,generated:1});
 const again=await call(route(),fullBody);assert.equal(again.status,200);assert.equal(generated,start+1);assert.deepEqual(again.data.segment_reuse,{reused:2,generated:0});
 const changed=await call(route(),{...fullBody,voice_segments:[fullBody.voice_segments[0],{text:'새로운 조각 수정',voice_id:body.voice_id}]});assert.equal(changed.status,200);assert.equal(generated,start+2);assert.deepEqual(changed.data.segment_reuse,{reused:1,generated:1});
 const voiceChanged=await call(route(),{...fullBody,voice_segments:[fullBody.voice_segments[0],{text:'새로운 조각',voice_id:'Changed'}]});assert.equal(voiceChanged.status,200);assert.equal(generated,start+3);
 const settingStart=generated; const settings=await call(route(),{...fullBody,speed:0.9,voice_segments:[fullBody.voice_segments[0]]});assert.equal(settings.status,200);assert.equal(generated,settingStart+1);
 const checkpoint=generated;failDownload=true;const unreadable=await call(route(),{...fullBody,voice_segments:[{text:'must not generate',voice_id:body.voice_id},fullBody.voice_segments[0]]});assert.equal(unreadable.status,500);assert.equal(generated,checkpoint);failDownload=false;
 assert(page.includes('if (useSubtitleVoiceSegments ||'), 'Full assembly errors must not fall back to paid browser synthesis');
 console.log('PASS: full narration reuses preview clips; unchanged repeat makes zero provider calls; text/voice change generates only one; unreadable cache fails before spending');
 console.log('PASS: cache bypass ignored; uncertain failure cannot spend credits again;  persistent reuse across reload, moved block reuse, Korean/voice invalidation, save failure, no selection auto-generation');
})().catch(e=>{console.error(e);process.exit(1)});

