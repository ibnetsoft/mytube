const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
function load(file,deps={}){const exports={};new Function('require','exports',ts.transpile(fs.readFileSync(file,'utf8'),{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}))((id)=>id in deps?deps[id]:require(id),exports);return exports}
const helper=load('auth-web/lib/stdSegmentAudioCache.ts');
const assets=[];let generated=0,uploads=0,failUpload=false;
const project={id:'10b3d223-1457-415a-ba40-7b947c6c1b3d',language:'ko'};
const db={storage:{from:()=>({upload:async()=>{uploads++;return {error:failUpload?{message:'offline'}:null}}})},from(table){let filters=[],inserted;const q={select(){return q},eq(k,v){filters.push([k,v]);return q},in(){return q},order(){return q},limit(){return q},insert(v){inserted=v;return q},async single(){const a={...inserted,id:String(assets.length+1)};assets.push(a);return {data:a}},async maybeSingle(){return {data:table==='std_projects'?project:assets.find(a=>filters.every(([k,v])=>(k.startsWith('metadata->>')?a.metadata[k.slice(11)]:a[k])===v))||null}}};return q}};
function route(){return load('auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts',{
    'next/server':{NextResponse:{json:(data,options)=>({data,status:options?.status||200})}},
    '@/lib/stdSegmentAudioCache':helper,'@/lib/supabaseAdmin':{supabaseAdmin:db},
    '@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:'test@example.com',user:{id:'test'}}})},
    '@/lib/stdGoogleDrive':{driveFileLink:()=>'',ensureStdProjectDriveFolders:()=>{throw Error('Must not use Drive')}},
    '@/lib/stdVoiceStudio':{generateVoiceStudioMp3:async()=>{generated++;return Buffer.alloc(300)}},
    '@/lib/voiceStudioCatalog':{isVoiceStudioVoice:()=>true,mergeVoiceStudioSegments:s=>s},
    '@/lib/stdTtsCompletion':{},'@/lib/stdLegacySync':{},'@/lib/stdMultiVoice':{},'@/lib/elevenLabsKeys':{}
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
 const page=fs.readFileSync('auth-web/app/std/page.tsx','utf8');assert(!page.includes('prefetchVrewSegment(selectedSubIndex)'));assert(!page.includes('requestSegmentAudio(true)'));assert(!page.includes('persistVrewSegmentAudio'));
 console.log('PASS: persistent reuse across reload, moved block reuse, Korean/voice invalidation, save failure, no selection auto-generation or failed-read regeneration');
})().catch(e=>{console.error(e);process.exit(1)});

