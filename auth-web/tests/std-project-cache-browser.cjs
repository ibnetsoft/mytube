const {chromium}=require('@playwright/test'),fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({headless:true,channel:"chrome"});try{
 const page=await browser.newPage();let version='v1',reads=0,revoked=false,forced=false
 await page.route('https://cache.test/**',async route=>{
   const req=route.request()
   if(new URL(req.url()).pathname==='/') return route.fulfill({contentType:'text/html',body:'<!doctype html><html></html>'})
   if(revoked) return route.fulfill({status:403,contentType:'application/json',body:'{"error":"forbidden"}'})
   const etag='"'+version+'"';const h=req.headers()
   if(h['if-none-match']===etag&&!h['x-std-refresh'])return route.fulfill({status:304,headers:{etag}})
   forced=!!h['x-std-refresh'];reads++
   return route.fulfill({contentType:'application/json',headers:{etag},body:JSON.stringify({project:{id:'p',version}})})
 })
 const source=ts.transpileModule(fs.readFileSync('lib/stdBrowserProjectCache.ts','utf8'),{compilerOptions:{module:1,target:9}}).outputText
 async function install(){await page.evaluate('(()=>{const exports={};'+source+';window.cachedRead=exports.fetchCachedProject})()')}
 async function read(token='a',force=false){return page.evaluate(async({token,force})=>{const r=await window.cachedRead('/p',{Authorization:'Bearer '+token},force);return{status:r.status,data:await r.json()}},{token,force})}
 await page.goto('https://cache.test/');await install();assert.equal((await read()).data.project.version,'v1');assert.equal(reads,1)
 await page.reload();await install();assert.equal((await read()).data.project.version,'v1');assert.equal(reads,1,'revisit must reuse IndexedDB')
 version='v2';assert.equal((await read()).data.project.version,'v2');assert.equal(reads,2)
 await read('b');assert.equal(reads,3,'other session cannot reuse cached entry')
 await read('a',true);assert.equal(forced,true);assert.equal(reads,4)
 revoked=true;assert.equal((await read()).status,403,'revocation must not return private cache')
 console.log('PASS: persistent browser cache, version change, account isolation, refresh and revoked access')
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})
