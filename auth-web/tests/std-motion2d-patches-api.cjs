const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript'),crypto=require('node:crypto'),sharp=require('sharp')
function fixture(options={}){
 const state={filters:[],writes:[],uploads:0,original:options.original}
 const db={from(table){let action='select',body;const q={select(){return q},eq(k,v){state.filters.push([table,k,v]);return q},in(){return q},order(){return q},limit(){return q},insert(v){action='insert';body=v;return q},single:async()=>{state.writes.push(body);return {data:{id:'patch',created_at:'now'}}},maybeSingle:async()=>({data:table==='std_projects'?{id:'p',status:'in_progress',...options.project}:options.sourceMissing?null:{id:'image'}}),then(resolve){return Promise.resolve({data:[],error:null}).then(resolve)}};return q}}
 const ex={},code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../app/api/std/projects/[projectId]/motion2d-patches/route.ts'),'utf8'),{compilerOptions:{module:1,target:9,esModuleInterop:true}}).outputText
 class NextResponse extends Response {static json(data,init){return Response.json(data,init)}}
 new Function('exports','require',code)(ex,name=>{if(name==='crypto')return crypto;if(name==='sharp')return sharp;if(name==='next/server')return {NextResponse};if(name.endsWith('supabaseAdmin'))return {supabaseAdmin:db};if(name.endsWith('stdWeb'))return {requireStdUser:async()=>options.unauthorized?{ok:false,response:Response.json({}, {status:401})}:{ok:true,requester:{email:'owner'}}};if(name.endsWith('stdSpeakerGeometry'))return {coordinateSource:()=>({bucket:'bucket',path:'source'})};if(name.endsWith('gcsStorage'))return {downloadGcsObject:async()=>state.original,uploadGcsBuffer:async()=>{state.uploads++;return {bucket:'bucket',path:'patch'}}};throw Error(name)})
 return {ex,state}
}
const params={params:{projectId:'p'}}
async function png(w,h,alpha){return sharp({create:{width:w,height:h,channels:4,background:{r:50,g:20,b:30,alpha}}}).png().toBuffer()}
function request(image,patch,role='mouth_closed'){const f=new FormData();f.set('scene','1');f.set('imageId','image');f.set('imageSha256',crypto.createHash('sha256').update(image).digest('hex'));f.set('role',role);f.set('file',new Blob([patch],{type:'image/png'}),'patch.png');return new Request('http://local',{method:'POST',body:f})}
test('only owner can register a matching, partially transparent patch',async()=>{
 const image=await png(8,8,1),patch=await sharp({create:{width:8,height:8,channels:4,background:{r:0,g:0,b:0,alpha:0}}}).composite([{input:await png(2,2,1),left:2,top:2}]).png().toBuffer()
 const no=fixture({original:image,unauthorized:true});assert.equal((await no.ex.POST(request(image,patch),params)).status,401);assert.equal(no.state.uploads,0)
 const f=fixture({original:image});assert.equal((await f.ex.POST(request(image,patch),params)).status,200);assert.equal(f.state.uploads,1);assert.equal(f.state.writes[0].metadata.kind,'motion2d_patch');assert.ok(f.state.filters.some(x=>x[1]==='employee_email'&&x[2]==='owner'))
 for(const bad of [await png(8,8,1),await png(4,4,.5)]){const x=fixture({original:image});assert.equal((await x.ex.POST(request(image,bad),params)).status,400);assert.equal(x.state.uploads,0)}
 const stale=fixture({original:await png(8,8,0)});assert.equal((await stale.ex.POST(request(image,patch),params)).status,400);assert.equal(stale.state.uploads,0)
 const closed=fixture({original:image,project:{submitted_at:'now'}});assert.equal((await closed.ex.POST(request(image,patch),params)).status,400);assert.equal(closed.state.uploads,0)
})
