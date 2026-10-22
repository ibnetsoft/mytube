const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {createSaveBeforeNavigationGuard}=require('./load-ts-module.cjs')(path.resolve(__dirname,'../lib/stdSaveBeforeNavigation.ts'));
test('navigation waits for saving and ignores duplicate destinations',async()=>{
 let dirty=true,finish;const events=[];
 const guard=createSaveBeforeNavigationGuard({needsSave:()=>dirty,save:()=>new Promise(resolve=>{finish=()=>{dirty=false;events.push('saved');resolve(true)}}),onError:()=>assert.fail(),onBusy:b=>events.push(b)});
 const first=guard(()=>events.push('moved'));
 assert.deepEqual(events,[true]);assert.equal(await guard(()=>events.push('duplicate')),false);
 finish();assert.equal(await first,true);assert.deepEqual(events,[true,'saved','moved',false]);
});
test('failed or rejected saves keep the page and report an error; retry can succeed',async()=>{
 for(const rejected of [true,false]){
  let dirty=true,fail=true,moved=0,errors=0;
  const guard=createSaveBeforeNavigationGuard({needsSave:()=>dirty,save:async()=>{if(fail){if(rejected)throw Error('offline');return false}dirty=false;return true},onError:()=>errors++});
  assert.equal(await guard(()=>moved++),false);assert.equal(moved,0);assert.equal(errors,1);
  fail=false;assert.equal(await guard(()=>moved++),true);assert.equal(moved,1);
 }
});
test('edits arriving during saving are flushed again before moving; unchanged pages skip saving',async()=>{
 let pending=2,saves=0,moved=false;
 const guard=createSaveBeforeNavigationGuard({needsSave:()=>pending>0,save:async()=>{pending--;saves++;return true},onError:()=>assert.fail()});
 assert.equal(await guard(()=>{moved=true}),true);assert.equal(saves,2);assert(moved);
 assert.equal(await guard(()=>{}),true);assert.equal(saves,2);
});
test('continuous edits never allow navigation with unsaved data',async()=>{
 let errors=0;
 const guard=createSaveBeforeNavigationGuard({needsSave:()=>true,save:async()=>true,onError:()=>errors++});
 assert.equal(await guard(()=>assert.fail('must not move')),false);assert.equal(errors,1);
});
test('navigation flush queues behind an actual in-flight subtitle save',async()=>{
 const {createSubtitleSaveQueue}=require('./load-ts-module.cjs')(path.resolve(__dirname,'../lib/stdSubtitlePersistence.ts'));
 const resolvers=[],bodies=[];let dirty=true,moved=false;
 const queue=createSubtitleSaveQueue(async(_url,options)=>{
  bodies.push(JSON.parse(options.body));
  return new Promise(resolve=>resolvers.push(()=>resolve({ok:true,status:200,json:async()=>({project:{id:'p'}})})));
 });
 const existing=queue('p',{draft:'older'},{});
 const guard=createSaveBeforeNavigationGuard({needsSave:()=>dirty,save:async()=>{await queue('p',{draft:'latest'},{});dirty=false;return true},onError:()=>assert.fail()});
 const leaving=guard(()=>{moved=true});
 const flush=async()=>{for(let i=0;i<15;i++)await Promise.resolve()};
 await flush();assert.deepEqual(bodies,[{draft:'older'}]);assert(!moved);
 resolvers.shift()();await existing;await flush();assert.deepEqual(bodies,[{draft:'older'},{draft:'latest'}]);assert(!moved);
 resolvers.shift()();assert.equal(await leaving,true);assert(moved);
});
