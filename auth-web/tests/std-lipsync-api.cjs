const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
function load(auth,db){
 const exports={},lib={};new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdLipSync.ts','utf8'),{module:1,target:7}))(lib,require);
 new Function('exports','require',ts.transpile(fs.readFileSync('app/api/std/projects/[projectId]/lipsync/route.ts','utf8'),{module:1,target:7}))(exports,name=>{
  if(name==='next/server')return {NextResponse:{json:(body,options)=>({body,status:options?.status||200})}};
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
  if(name.includes('stdWeb'))return {requireStdUser:async()=>auth};
  if(name.includes('stdComic'))return {isComicProject:()=>false};
  if(name.includes('stdLipSync'))return lib;
  throw new Error(name);
 });return exports;
}
test('unauthenticated requests never read project data or enqueue jobs',async()=>{
 const routes=load({ok:false,response:{status:401}},{from:()=>{throw Error('must not query')}});
 assert.equal((await routes.POST({}, {params:{projectId:'other'}})).status,401);
});
test('project access is limited to the requester employee email',async()=>{
 const filters={};const q={select:()=>q,eq:(k,v)=>{filters[k]=v;return q;},maybeSingle:async()=>({data:null})};
 const routes=load({ok:true,requester:{email:'owner@test'}},{from:()=>q});
 assert.equal((await routes.GET({}, {params:{projectId:'foreign'}})).status,404);
 assert.equal(filters.employee_email,'owner@test');
});
test('status exposes credential presence, never the key, and explains missing TTS',async()=>{
 const db={from:table=>{const q={select:()=>q,eq:()=>q,order:async()=>({data:[]}),maybeSingle:async()=>({data:table==='std_projects'?{id:'project',project_payload:{}}:{value:'private-hedra-key'}})};return q;}};
 const routes=load({ok:true,requester:{email:'owner@test'}},db),r=await routes.GET({}, {params:{projectId:'project'}});
 assert.equal(r.status,200);assert.equal(r.body.configured,true);assert.ok(r.body.preparationError);
 assert.equal(JSON.stringify(r.body).includes('private-hedra-key'),false);
});
test('concurrent retries share one atomic claim and enqueue only one paid generation',async()=>{
 const lib={};new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdLipSync.ts','utf8'),{module:1,target:7}))(lib,require);
 const subs=[{text:'대사',start:0,end:1,voice_id:'v',dialogue_kind:'dialogue',dialogue_speaker:'소녀',scene_number:1}];
 const project={id:'p',updated_at:'now',project_payload:{subtitles:subs}},scenes=[{id:'s',scene_number:1}];
 const assets=[{id:'audio',asset_type:'audio',status:'assigned',metadata:{subtitle_timeline:subs}},
  {id:'image',scene_number:1,asset_type:'image',status:'assigned',metadata:{gcs_path:'image.png'}}];
 const fingerprint=lib.lipSyncPlan(project,scenes,assets)[0].fingerprint;
 assets.push({id:'previous-job',metadata:{kind:'lipsync_job',state:'failed',fingerprint}});
 const claims=new Set();let inserted=0;
 const db={storage:{from:()=>({upload:async path=>{if(claims.has(path))return {error:{message:'duplicate'}};claims.add(path);return {};},remove:async()=>({})})},from:table=>{
  let mutation;const q={select:()=>mutation?.update?Promise.resolve({data:[{id:'p'}]}):q,eq:()=>q,
   order:async()=>({data:table==='std_project_scenes'?scenes:assets}),
   maybeSingle:async()=>({data:table==='std_projects'?project:{value:'key'}}),
   update:row=>{mutation={update:row};return q;},insert:row=>{mutation={insert:row};inserted++;return q;},
   single:async()=>({data:{id:'new-job',...mutation.insert}})};return q;
 }};
 const routes=load({ok:true,requester:{email:'owner@test'}},db);
 const req=()=>({json:async()=>({action:'retry',scene_number:1,fingerprint,points:{'소녀':[.5,.5]}})});
 const results=await Promise.all([routes.POST(req(),{params:{projectId:'p'}}),routes.POST(req(),{params:{projectId:'p'}})]);
 assert.equal(inserted,1);assert.equal(results.filter(r=>r.status===200).length,1);
});
