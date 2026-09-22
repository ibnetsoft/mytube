const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../worker/codex_console/refresh.js'),'utf8');

function fixture(){
  const fields=[{id:'history-search',value:'작성 중인 검색어',type:'text',tagName:'INPUT'},
    {id:'notes',value:'지켜야 할 대본 방향',type:'textarea',tagName:'TEXTAREA'}];
  const button={disabled:false,setAttribute(){},removeAttribute(){}};
  const nodes=Object.fromEntries(fields.map(f=>[f.id,f]));
  Object.assign(nodes,{refresh:button,'view-repair':{hidden:true},'view-jobs':{hidden:false}});
  const saved=new Map(),messages=[],calls=[];let ready;
  const context={console,Date,Set,JSON,Number,Boolean,Math,
    $:id=>nodes[id],page:2,historyPage:1,currentSource:null,selectedJob:{id:'a'.repeat(32),origin:'dedicated'},topicCountryOverridden:false,
    document:{querySelector:()=>({id:'view-jobs'}),querySelectorAll:selector=>selector==='input,textarea,select'?fields:[],
      addEventListener:(event,callback)=>{ready=callback;}},
    sessionStorage:{setItem:(k,v)=>saved.set(k,v),getItem:k=>saved.get(k),removeItem:k=>saved.delete(k)},
    window:{scrollY:210,newCountryOverridden:true,categoriesReady:Promise.resolve(),
      location:{reload:()=>calls.push('reload')},scrollTo:()=>{},updateNewSettingSummary:()=>{}},
    notice:m=>messages.push(m),error:m=>messages.push(m),view:v=>calls.push('view:'+v),
    loadHistory:async()=>calls.push('history'),showJob:async(id)=>calls.push('job:'+id),refresh:async()=>calls.push('refresh')};
  vm.createContext(context);vm.runInContext(source,context);
  return {context,fields,button,saved,messages,calls,ready:()=>ready()};
}

test('full reload restores draft, search, page and selected result',async()=>{
  const f=fixture();await f.button.onclick();
  assert.equal(f.button.disabled,true);assert.deepEqual(f.calls,['reload']);
  f.fields.forEach(field=>field.value='');f.context.historyPage=0;
  await f.ready();
  assert.equal(f.fields[0].value,'작성 중인 검색어');
  assert.equal(f.fields[1].value,'지켜야 할 대본 방향');
  assert.equal(f.context.historyPage,1);
  assert.ok(f.calls.includes('view:jobs'));assert.ok(f.calls.includes('job:'+'a'.repeat(32)));
  assert.equal(f.saved.size,0);
});

test('storage failure preserves the current page instead of discarding input',async()=>{
  const f=fixture();f.context.sessionStorage.setItem=()=>{throw Error('storage unavailable');};
  await f.button.onclick();assert.equal(f.calls.includes('reload'),false);assert.equal(f.button.disabled,false);
  assert.match(f.messages[0],/새로고침을 중단/);
});

test('selected file prevents navigation and refreshes data',async()=>{
  const f=fixture();f.context.document.querySelectorAll=s=>s==='input[type=file]'?[{files:[{}]}]:[];
  await f.button.onclick();assert.equal(f.calls.includes('reload'),false);assert.ok(f.calls.includes('refresh'));
  assert.equal(f.button.disabled,false);
});
