const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), ts = require('typescript'), path = require('path')
function load(file,mocks={}) { const ex={}; new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:1,target:9}}).outputText)(ex,n=>mocks[n]||require(n)); return ex }
test('compressed server cache is scoped and tolerates corrupt entries',async()=>{
 const cache=new Map(); const lib=load('lib/stdProjectReadCache.ts',{'./server-cache':{getServerCache:async k=>cache.get(k),setServerCache:async(k,v,ttl)=>{assert.equal(ttl,60);cache.set(k,v)}}})
 const a=lib.projectReadCacheKey('a','p','v1'),b=lib.projectReadCacheKey('b','p','v1')
 assert.notEqual(a,b); assert.notEqual(a,lib.projectReadCacheKey('a','p','v2'))
 const value={project:{script:'text'.repeat(100000)}}
 await lib.cacheProjectResponse(a,value); assert.deepEqual(await lib.readProjectResponse(a),value); assert.equal(await lib.readProjectResponse(b),null)
 cache.set(a,'corrupt'); assert.equal(await lib.readProjectResponse(a),null)
})
test('IndexedDB unavailable still permits authorized live reads and refresh bypass',async()=>{
 global.crypto=require('node:crypto').webcrypto
 let seen
 global.fetch=async(url,options)=>{seen=options;return Response.json({project:{id:'p'}})}
 const lib=load('lib/stdBrowserProjectCache.ts')
 assert.equal((await (await lib.fetchCachedProject('/p',{Authorization:'Bearer token'})).json()).project.id,'p')
 assert.equal(seen.headers['If-None-Match'],undefined)
 await lib.fetchCachedProject('/p',{Authorization:'Bearer token'},true); assert.equal(seen.headers['x-std-refresh'],'1')
})
test('project reads authenticate and check ownership before Redis or conditional response',async()=>{
 let owner='owner@example.test',email=owner,reads=0,authOk=true
 const mocks={
  '@/lib/stdWeb':{requireStdUser:async()=>authOk?{ok:true,requester:{email}}:{ok:false,response:new Response(null,{status:401})}},
  '@/lib/supabaseAdmin':{supabaseAdmin:{rpc:async()=>({data:{employee_email:owner,version:'v1'}}),from:()=>assert.fail('Unchanged cached project must not download tables')}},
  '@/lib/stdProjectReadCache':{projectReadCacheKey:()=> 'key',readProjectResponse:async()=>{reads++;return{project:{id:'p'}}},cacheProjectResponse:async()=>{}},
  'next/server':{NextResponse:Response},
 }
 const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(__dirname,'../app/api/std/projects/[projectId]/route.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText)(ex,n=>mocks[n]||(n.startsWith('@/')?{}:require(n)))
 const request=()=>new Request('https://studio.test/api/std/projects/p',{headers:{'if-none-match':'"std-read-v1-v1"'}})
 assert.equal((await ex.GET(request(),{params:{projectId:'p'}})).status,304);assert.equal(reads,0)
 email='other@example.test';assert.equal((await ex.GET(request(),{params:{projectId:'p'}})).status,204);assert.equal(reads,0)
 authOk=false;assert.equal((await ex.GET(request(),{params:{projectId:'p'}})).status,401);assert.equal(reads,0)
 authOk=true;email=owner;assert.equal((await ex.GET(new Request('https://studio.test/p'),{params:{projectId:'p'}})).status,200);assert.equal(reads,1)
})
