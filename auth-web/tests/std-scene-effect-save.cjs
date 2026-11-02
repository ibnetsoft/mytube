const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), ts = require('typescript'), path = require('node:path')
function route(auth, rpc) {
 const src=fs.readFileSync(path.join(__dirname,'../app/api/std/projects/[projectId]/scene-effects/route.ts'),'utf8')
 const exports={}
 const mocks={'next/server':{NextResponse:Response},'@/lib/stdWeb':{requireStdUser:auth},'@/lib/supabaseAdmin':{supabaseAdmin:{rpc}}}
 new Function('exports','require',ts.transpileModule(src,{compilerOptions:{module:1,target:9}}).outputText)(exports,n=>mocks[n]||require(n))
 return exports
}
const id='53195c94-2ea7-4748-b413-db41265ebfaa'
const request=body=>new Request('https://example.test/api',{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify(body)})
const user=async()=>({ok:true,requester:{email:'owner@example.test'}})
test('saves only selected numbers and the selected effect',async()=>{
 let args
 const api=route(user,async(name,params)=>{assert.equal(name,'std_save_scene_effect');args=params;return {data:{success:true},error:null}})
 const res=await api.PATCH(request({field:'transition_effect',value:'none',scene_numbers:[21,22]}),{params:{projectId:id}})
 assert.equal(res.status,200);assert.deepEqual(args.p_numbers,[21,22]);assert.equal(args.p_owner,'owner@example.test');assert.equal(args.p_value,'none')
})
test('rejects unauthenticated and malformed requests without writing',async()=>{
 let writes=0;const rpc=async()=>{writes++;return {data:{success:true}}}
 assert.equal((await route(async()=>({ok:false,response:new Response(null,{status:401})}),rpc).PATCH(request({}),{params:{projectId:id}})).status,401)
 const api=route(user,rpc)
 for(const body of [{field:'script',value:'x',scene_numbers:[1]},{field:'transition_effect',value:'x',scene_numbers:[1,1]},{field:'transition_effect',value:'x',scene_numbers:[0]}])
  assert.equal((await api.PATCH(request(body),{params:{projectId:id}})).status,400)
 assert.equal(writes,0)
})
test('reports locked or missing projects without reporting success',async()=>{
 for(const [error,status] of [['locked',409],['not_found',404],['missing_scene',400]]) {
  const api=route(user,async()=>({data:{error},error:null}))
  assert.equal((await api.PATCH(request({field:'image_effect',value:'none',scene_numbers:[21]}),{params:{projectId:id}})).status,status)
 }
})
