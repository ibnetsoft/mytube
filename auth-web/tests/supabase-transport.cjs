const assert = require('node:assert/strict')
const load = require('./load-ts-module.cjs')
const { createSupabaseTransport } = load(require('node:path').join(__dirname, '../lib/supabaseTransport.ts'))
;(async () => {
 let now=100, calls=0, mode='down', release
 const transport=createSupabaseTransport({now:()=>now, cooldownMs:30, fetch:async (_url,init)=>{
  calls++; assert.equal(init.cache,'no-store')
  if(mode==='down')return new Response('down',{status:522})
  if(mode==='probe')return new Promise(resolve=>{release=()=>resolve(new Response('ok'))})
  return new Response('ok')
 }})
 assert.equal((await transport('https://example.test')).status,522)
 assert.equal((await transport('https://example.test')).status,503)
 assert.equal(calls,1)
 now+=31; mode='probe'
 const probe=transport('https://example.test')
 assert.equal((await transport('https://example.test')).status,503)
 assert.equal(calls,2); release(); assert.equal((await probe).status,200)
 mode='ok'; assert.equal((await transport('https://example.test')).status,200)
 let writes=0
 const timed=createSupabaseTransport({timeoutMs:5,fetch:async (_url,init)=>{
  writes++; return new Promise((_,reject)=>init.signal.addEventListener('abort',()=>reject(init.signal.reason),{once:true}))
 }})
 const result=await timed('https://example.test',{method:'POST'})
 assert.equal(result.status,503); assert.equal(result.headers.get('retry-after'),'30')
 assert.equal(writes,1)
 assert.equal((await timed('https://example.test',{method:'POST'})).status,503); assert.equal(writes,1)
 const controller=new AbortController(); controller.abort()
 const canceled=createSupabaseTransport({fetch:async (_url,init)=>{if(init.signal.aborted)throw init.signal.reason;return new Response('ok')}})
 await assert.rejects(canceled('https://example.test',{signal:controller.signal}))
 assert.equal((await canceled('https://example.test')).status,200)
 console.log('PASS outage cooldown, single recovery probe, timeout without write replay, caller cancellation')
})().catch(error=>{console.error(error);process.exitCode=1})
