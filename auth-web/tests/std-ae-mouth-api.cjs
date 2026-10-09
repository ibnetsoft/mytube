const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
function load(auth,db,lib={}){
 const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('app/api/std/projects/[projectId]/ae-mouth/route.ts','utf8'),{module:1,target:7}))(ex,name=>{
  if(name==='next/server')return {NextResponse:{json:(body,options)=>({body,status:options?.status||200})}};
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
  if(name.includes('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:[],error:null})};
  if(name.includes('stdWeb'))return {requireStdUser:async()=>auth};
  if(name.includes('stdAeMouthQueue'))return {ensureAeMouthJob:()=>{throw Error('unexpected generation')}};
  if(name.includes('stdAeMouth'))return lib;
  throw Error(name);
 });return ex;
}
test('both status and mutation reject unauthenticated access before database queries',async()=>{
 const route=load({ok:false,response:{status:401}},{from:()=>{throw Error('must not query')}});
 assert.equal((await route.GET({}, {params:{projectId:'p'}})).status,401);
 assert.equal((await route.POST({}, {params:{projectId:'p'}})).status,401);
});
test('project is scoped to employee email',async()=>{
 const filters={};const q={select:()=>q,eq:(k,v)=>{filters[k]=v;return q;},maybeSingle:async()=>({data:null})};
 const route=load({ok:true,requester:{email:'owner@test'}},{from:()=>q});
 assert.equal((await route.GET({}, {params:{projectId:'foreign'}})).status,404);
 assert.equal(filters.employee_email,'owner@test');
});
test('only ready directions start AE; unresolved scenes stay pending',async()=>{
 let job={id:'job',updated_at:'old',metadata:{state:'direction_pending',fingerprint:'current',results:[{number:19,status:'direction_pending',direction:'girl mouth only',visibility:[]}]}};
 let mutation;
 const db={from:table=>{const q={select:()=>q,eq:()=>q,order:async()=>({data:[]}),update:v=>{mutation=v;return q;},maybeSingle:async()=>({data:table==='std_projects'?{id:'p',project_payload:{}}:{id:'job'}})};return q;}};
 const route=load({ok:true,requester:{email:'owner@test'}},db,{aeMouthInput:()=>({fingerprint:'newly-added-coordinates'}),currentAeMouthJob:()=>job});
 const request=f=>({json:async()=>({action:'approve_direction',fingerprint:f})});
 assert.equal((await route.POST(request('stale'),{params:{projectId:'p'}})).status,409);assert.equal(mutation,undefined);
 job.metadata.results.push({number:20,status:'needs_review'});
 assert.equal((await route.POST(request('current'),{params:{projectId:'p'}})).status,200);
 assert.equal(mutation.metadata.results[1].status,'needs_review');
 assert.equal((await route.POST(request('current'),{params:{projectId:'p'}})).status,200);
 assert.equal(mutation.metadata.state,'direction_approved');assert.equal(mutation.metadata.results[0].status,'direction_approved');
});
