const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), ts = require('typescript')
function load(file, deps={}) {
 const out={};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:1,target:9}}).outputText
 new Function('exports','require',code)(out,name=>name in deps?deps[name]:require(name));return out
}
const store=load('lib/stdProjectTitleTranslations.ts'), titles=load('lib/stdTopicTitle.ts')
const a='11111111-1111-4111-8111-111111111111', b='22222222-2222-4222-8222-222222222222'
function fixture() {
 const state={projects:[{id:a,title:'原題',topic_queue_id:1,employee_email:'owner@test',list_deleted_at:null},{id:b,title:'別題',topic_queue_id:2,employee_email:'other@test',list_deleted_at:null}],topics:[],saved:[],calls:0,failSave:false}
 const db={from(table){const filters=[];let rows=null;const q={select(){return q},eq(k,v){filters.push(x=>x[k]===v);return q},is(k,v){return q.eq(k,v)},in(k,v){filters.push(x=>v.includes(x[k]));return q},maybeSingle(){return Promise.resolve({data:{value:'test-key'},error:null})},upsert(v){rows=v;return q},then(resolve,reject){return Promise.resolve().then(()=>{
  if(rows){if(state.failSave)return {error:new Error('save failed')};for(const row of rows)if(!state.saved.some(x=>x.project_id===row.project_id&&x.source_hash===row.source_hash&&x.locale===row.locale))state.saved.push(row);return {error:null}}
  const data=table==='std_projects'?state.projects:table==='topics_queue'?state.topics:state.saved
  return {data:data.filter(x=>filters.every(f=>f(x))),error:null}
 }).then(resolve,reject)}};return q}}
 const route=load('app/api/std/projects/title-translations/route.ts',{
  'next/server':{NextResponse:{json:(body,options)=>({status:options?.status||200,json:async()=>body})}},
  '@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:'owner@test'}})},
  '@/lib/supabaseAdmin':{supabaseAdmin:db}, '@/lib/stdTopicTitle':titles,
  '@/lib/stdProjectTitleTranslations':store,
  '@/lib/stdTitleTranslation':{generateStdTitleTranslation:async(_db,prompt)=>{state.calls++;if(state.failModel)throw Error('model unavailable');const rows=JSON.parse(prompt.slice(prompt.indexOf('Titles: ')+8));return JSON.stringify({translations:rows.map(row=>({id:row.id,title:row.title==='原題'?'원제':'새 제목'}))})}},
 })
 const post=(locale='ko',ids=[a])=>route.POST(new Request('https://test/api',{method:'POST',body:JSON.stringify({locale,ids})}))
 return {state,db,post}
}
test('refresh and independent requests read durable title without another model call',async()=>{
 const {state,db,post}=fixture();assert.equal((await post()).status,200);assert.equal(state.calls,1)
 const saved=await store.loadSavedProjectTitleTranslations(db,state.projects.slice(0,1));assert.equal(saved.get(a).ko,'원제')
 assert.equal(titles.localizedProjectTitle({...state.projects[0],title_translations:saved.get(a)},'ko'),'원제')
 assert.equal((await (await post()).json()).translations[0].title,'원제');assert.equal(state.calls,1)
 await post('th');assert.equal(state.calls,2);assert.equal(state.saved.length,2)
 state.projects[0].title='新題';await post();assert.equal(state.calls,3)
 assert.equal((await store.loadSavedProjectTitleTranslations(db,state.projects.slice(0,1))).get(a).ko,'새 제목')
})
test('reuse existing topic/project DB translations before calling the model',async()=>{
 const {state,post}=fixture();state.topics=[{id:1,topic:'原題',generated_title:'原題',progress_titles:{ko:'기존 토픽 번역'}}]
 assert.equal((await (await post()).json()).translations[0].title,'기존 토픽 번역');assert.equal(state.calls,0)
 const next=fixture();next.state.projects[0].project_titles={ko:'기존 프로젝트 번역'};await next.post();assert.equal(next.state.calls,0)
})
test('changed topic title is not reused for a different project title',async()=>{
 const {state,post}=fixture();state.topics=[{id:1,generated_title:'旧題',progress_titles:{ko:'옛 제목'}}]
 assert.equal((await (await post()).json()).translations[0].title,'원제');assert.equal(state.calls,1)
})
test('ownership/deletion restrictions and failed persistence never return unsaved success',async()=>{
 const {state,post}=fixture();assert.deepEqual((await (await post('ko',[b])).json()).translations,[]);assert.equal(state.calls,0)
 state.failSave=true;const old=console.error;console.error=()=>{};try{assert.equal((await post()).status,503)}finally{console.error=old}
 state.projects[0].list_deleted_at='deleted';assert.deepEqual((await (await post()).json()).translations,[])
 assert.equal((await post('invalid')).status,400)
})

test('model outage preserves saved translations in a mixed request',async()=>{
 const {state,post}=fixture();await post();state.failModel=true
 state.projects.push({id:'33333333-3333-4333-8333-333333333333',title:'新題',employee_email:'owner@test',list_deleted_at:null})
 const old=console.warn;console.warn=()=>{}
 try {const response=await post('ko',[a,state.projects[2].id]);assert.equal(response.status,200);assert.deepEqual((await response.json()).translations,[{id:a,source:'原題',title:'원제'}])} finally {console.warn=old}
})
