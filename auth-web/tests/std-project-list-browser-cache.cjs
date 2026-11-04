const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), ts = require('typescript'), path = require('path')
function load(file) { const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:1,target:9}}).outputText)(ex,require);return ex }
const list = load('lib/stdBrowserProjectListCache.ts')
function storage() { const values=new Map();return {values,getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)} }
test('saved list is scoped, expires, omits private payloads, and tolerates storage errors',()=>{
 const store=storage(), a=list.projectListScope('A@EXAMPLE.COM'), b=list.projectListScope('b@example.com'), imp=list.projectListScope('a@example.com','b@example.com')
 const source=[{id:'p1',title:'Title',category_name:'Japan',step_status:{allDone:true},thumbnail_url:'https://storage.test/image?token=secret',project_payload:{script:'secret'},progress_payload:{private:'secret'}}]
 list.writeProjectListSnapshot(store,a,source,1000)
 assert.deepEqual(list.readProjectListSnapshot(store,a,1001),[{id:'p1',title:'Title',category_name:'Japan',step_status:{allDone:true}}])
 list.saveProjectListTitleTranslations(store,a,'ko',[{id:'p1',source:'wrong title',title:'잘못된 번역'}],1001)
 assert.equal(list.readProjectListSnapshot(store,a,1001)[0].title_localization,undefined)
 list.saveProjectListTitleTranslations(store,a,'ko',[{id:'p1',source:'Title',title:'제목'}],1001)
 assert.equal(list.readProjectListSnapshot(store,a,1001)[0].title_localization.title_translations.ko,'제목')
 list.writeProjectListSnapshot(store,a,source,2000)
 assert.equal(list.readProjectListSnapshot(store,a,2001)[0].title_localization.title_translations.ko,'제목')
 assert.equal(list.readProjectListSnapshot(store,b,1001),null);assert.equal(list.readProjectListSnapshot(store,imp,1001),null)
 assert.equal(list.readProjectListSnapshot(store,a,2000+24*60*60*1000+1),null)
 list.clearProjectListSnapshot(store,a);assert.equal(list.readProjectListSnapshot(store,a,1001),null)
 const broken={getItem(){throw Error('blocked')},setItem(){throw Error('blocked')},removeItem(){throw Error('blocked')}}
 assert.equal(list.readProjectListSnapshot(broken,a),null);assert.doesNotThrow(()=>list.writeProjectListSnapshot(broken,a,source));assert.doesNotThrow(()=>list.clearProjectListSnapshot(broken,a))
})
test('startup and modal share a request only within the same session and return independent bodies',async()=>{
 const old=global.fetch;let calls=0,release;global.fetch=()=>{calls++;return new Promise(resolve=>{release=()=>resolve(Response.json({projects:[{id:'p'}]}))})}
 try {
  const headers={Authorization:'Bearer a'}, one=list.fetchSharedProjectList('/api/std/projects',headers), two=list.fetchSharedProjectList('/api/std/projects',headers)
  assert.equal(calls,1);release();assert.deepEqual(await (await one).json(),{projects:[{id:'p'}]});assert.deepEqual(await (await two).json(),{projects:[{id:'p'}]})
  const another=list.fetchSharedProjectList('/api/std/projects',{Authorization:'Bearer b'});assert.equal(calls,2);release();await another
 } finally {global.fetch=old}
})
