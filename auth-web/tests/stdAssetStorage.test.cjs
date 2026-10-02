const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
function load(path, deps) {
 const exports = {};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(path,'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
 {exports,require: name => deps[name],Buffer,URL,Uint8Array,console,process:{env:{NEXT_PUBLIC_SUPABASE_URL:"https://storage.test",SUPABASE_SERVICE_ROLE_KEY:"test-key"}},fetch:deps.fetch});
 return exports;
}
const root = __dirname+'/../';
const {assetStorageRef} = load(root+'lib/stdAssetStorage.ts',{});
test('legacy storage and secondary GCS copies retain primary backend',()=>{
 assert.equal(assetStorageRef({storage_bucket:'content-assets',storage_path:'a',gcs_path:'a',secondary_storage_provider:'gcs'}).provider,'supabase');
 assert.equal(assetStorageRef({storage_provider:'gcs',storage_bucket:'bucket',storage_path:'a'}).provider,'supabase');
 assert.equal(assetStorageRef({gcs_bucket:'bucket',gcs_path:'a'}).provider,'supabase');
});
function harness({authorized=true,project=true,asset=true,missing=false,storageError=false,gcsMissing=false,metadata}={}) {
 let signed=0, ranged='', gcs=0;
 const row={id:'asset',asset_type:'other',mime_type:'audio/mpeg',metadata:metadata || {storage_bucket:'content-assets',storage_path:'a'}};
 const db={from(table){const q={select(){return q},eq(){return q},in(){return q},limit(){return q},async maybeSingle(){return {data:table==='std_projects'?(project?{id:'p'}:null):(asset?row:null)}}};return q},storage:{from(){return {async createSignedUrl(){signed++;if(missing)return {error:{statusCode:404,message:'Object not found'}};if(storageError)return {error:{statusCode:403,message:'Forbidden'}};return {data:{signedUrl:'https://storage.test/a'}}}}}}};
 const route=load(root+'app/api/std/projects/[projectId]/assets/file/route.ts',{
  'next/server':{NextResponse:Response},'@/lib/supabaseAdmin':{supabaseAdmin:db},
  '@/lib/stdWeb':{requireStdUser:async()=>authorized?{ok:true,requester:{email:'owner'}}:{ok:false,response:new Response(null,{status:401})}},
  '@/lib/stdAssetStorage':{assetStorageRef},'@/lib/gcsStorage':{isGcsConfiguredAsync:()=>true, downloadGcsObjectViaSignedUrl:async(args)=>{gcs++;assert.equal(args.range,'bytes=0-2');if(gcsMissing)throw Error('Object not found');return {buffer:Buffer.from([4,5,6]),status:206,contentRange:'bytes 0-2/30',contentLength:'3',contentType:'audio/mpeg'}}},
  fetch:async(url,options)=>{signed++;assert.equal(options.headers.Authorization,'Bearer test-key');if(missing)return Response.json({message:'Object not found'},{status:400});if(storageError)return Response.json({message:'Forbidden'},{status:403});ranged=options.headers.Range;return new Response(new Uint8Array([1,2,3]),{status:206,headers:{'content-type':'audio/mpeg','content-range':'bytes 0-2/30','content-length':'3'}})},
 });
 return {get:()=>route.GET(new Request('https://app.test/file?assetId=asset',{headers:{Range:'bytes=0-2'}}),{params:{projectId:'10b3d223-1457-415a-ba40-7b947c6c1b3d'}}),stats:()=>({signed,ranged,gcs})};
}
test('authorized legacy segment audio streams ranged bytes without GCS',async()=>{const h=harness();const r=await h.get();assert.equal(r.status,206);assert.equal(r.headers.get('X-STD-Media-Source'),'supabase');assert.equal((await r.arrayBuffer()).byteLength,3);assert.equal(h.stats().ranged,'bytes=0-2')});
for(const scenario of [{authorized:false,status:401},{project:false,status:404},{asset:false,status:404}])test('denies unauthorized/missing resource '+JSON.stringify(scenario),async()=>{const h=harness(scenario);assert.equal((await h.get()).status,scenario.status);assert.equal(h.stats().signed,0)});

test('Supabase success never reads GCS',async()=>{const h=harness();await h.get();assert.equal(h.stats().gcs,0)});
test('Supabase missing falls through to GCS preserving range',async()=>{const h=harness({missing:true});const r=await h.get();assert.equal(r.status,206);assert.equal(r.headers.get('X-STD-Media-Source'),'gcs');assert.equal(h.stats().signed,1);assert.equal(h.stats().gcs,1)});
test('both copies missing returns 404',async()=>{const h=harness({missing:true,gcsMissing:true});assert.equal((await h.get()).status,404)});
test('permission failure is not a missing file',async()=>{const h=harness({storageError:true});assert.equal((await h.get()).status,502);assert.equal(h.stats().gcs,0)});

test('browser stored asset URL uses the priority reader instead of GCS direct URL',()=>{
 const {resolveFastAssetUrl}=load(root+'lib/stdMediaLoading.ts',{});
 assert.equal(resolveFastAssetUrl('p',{id:'a',metadata:{gcs_path:'file',gcs_public_url:'https://gcs.test/file'}}),'/api/std/projects/p/assets/file?assetId=a');
});

test('GCS primary audio skips Supabase and preserves byte range',async()=>{
 const h=harness({metadata:{storage_provider:'gcs',storage_bucket:'gcs-bucket',storage_path:'a',gcs_bucket:'gcs-bucket',gcs_path:'a'}});
 const r=await h.get();assert.equal(r.status,206);assert.equal(r.headers.get('X-STD-Media-Source'),'gcs');assert.equal(h.stats().signed,0);assert.equal(h.stats().gcs,1);
});
test('legacy GCS archive is played before Supabase',async()=>{
 const h=harness({metadata:{storage_bucket:'content-assets',storage_path:'a',gcs_bucket:'gcs-bucket',gcs_path:'a'}});
 assert.equal((await h.get()).headers.get('X-STD-Media-Source'),'gcs');assert.equal(h.stats().signed,0);
});
test('legacy archive failure can reuse Supabase without generation',async()=>{
 const h=harness({gcsMissing:true,metadata:{storage_bucket:'content-assets',storage_path:'a',gcs_bucket:'gcs-bucket',gcs_path:'a'}});
 assert.equal((await h.get()).headers.get('X-STD-Media-Source'),'supabase');assert.equal(h.stats().signed,1);
});
test('new audio persistence stores GCS metadata without a Supabase upload',async()=>{
 const calls=[];
 const {persistSegmentAudio}=load(root+'lib/stdSegmentAudioCache.ts',{
  crypto:require('node:crypto'), '@/lib/gcsStorage':{isGcsConfiguredAsync:async()=>true,uploadGcsBuffer:async(args)=>{calls.push('gcs');assert.equal(args.buffer.toString(),'audio');return {bucket:'gcs-bucket',path:args.objectPath}}}
 });
 let inserted;
 const db={from:()=>({insert(row){calls.push('db');inserted=row;return {select:()=>({single:async()=>({data:row})})}}}),storage:{from(){throw Error('Unexpected Supabase upload')}}};
 await persistSegmentAudio(db,{projectId:'p',cacheKey:'k',identity:{text:'same'},audioBuffer:Buffer.from('audio'),fileName:'a.mp3',segmentIndex:0,generatedBy:'owner'});
 assert.deepEqual(calls,['gcs','db']);assert.equal(inserted.metadata.storage_provider,'gcs');assert.equal(inserted.metadata.storage_bucket,'gcs-bucket');
});
