const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),path=require('node:path')
function makeRoute() {
 const selects=[]
 const db={from(table){const q={select(columns){selects.push({table,columns});return q},eq(){return q},order(){return q},limit(){return q},async maybeSingle(){return table==='std_projects'?{data:{id:'p',employee_email:'user@test',script:'script',subtitles:[],voice_id:'v',tts_speed:1},error:null}:{data:null,error:null}}};return q}}
 const mocks={'next/server':{NextResponse:Response},'@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:'user@test',user:{id:'u'}}})},'@/lib/supabaseAdmin':{supabaseAdmin:db},'@/lib/stdTtsJobs':{publicTtsJob:x=>x},'@/lib/stdSubtitleSpeakerProgress':{}}
 const exports={}; const code=fs.readFileSync(path.join(__dirname,'../app/api/std/projects/[projectId]/tts/jobs/route.ts'),'utf8')
 new Function('exports','require',ts.transpileModule(code,{compilerOptions:{module:1,target:9}}).outputText)(exports,n=>mocks[n]||require(n))
 return {api:exports,selects}
}
test('polling verifies ownership without loading large project payload',async()=>{
 const {api,selects}=makeRoute();const r=await api.GET(new Request('https://example.test'),{params:{projectId:'p'}})
 assert.equal(r.status,200);assert.equal(selects[0].columns,'id,employee_email')
})
test('TTS creation reads only required speech fields',async()=>{
 const {api,selects}=makeRoute();const r=await api.POST(new Request('https://example.test',{method:'POST',body:'{}'}),{params:{projectId:'p'}})
 assert.equal(r.status,400);assert.match(selects[0].columns,/script:project_payload->>script/);assert.doesNotMatch(selects[0].columns,/,project_payload$/)
})
