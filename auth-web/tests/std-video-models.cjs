const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), ts = require('typescript')
const load = require('./load-ts-module.cjs'), validation = load('lib/stdVideoModels.ts')
function fixture() {
 const state = { email: 'one@test.local', auth: true, rows: new Map() }, exports = {}
 const crypto = require('crypto'), key = crypto.randomBytes(32)
 function encrypt(value) { const iv=crypto.randomBytes(12), c=crypto.createCipheriv('aes-256-gcm',key,iv); return [iv,c.update(JSON.stringify(value)),c.final(),c.getAuthTag()].map(x=>x.toString('base64')).join('.') }
 function decrypt(value) { const [iv,data,end,tag]=value.split('.').map(x=>Buffer.from(x,'base64')); const d=crypto.createDecipheriv('aes-256-gcm',key,iv);d.setAuthTag(tag);return JSON.parse(Buffer.concat([d.update(Buffer.concat([data,end])),d.final()]).toString()) }
 new Function('exports','require',ts.transpileModule(fs.readFileSync('app/api/std/video-models/route.ts','utf8'),{compilerOptions:{module:1,target:7}}).outputText)(exports,name=>{
  if(name==='crypto')return crypto
  if(name==='next/server')return {NextResponse:{json:(body,options={})=>({body,status:options.status||200})}}
  if(name.includes('stdWeb'))return {requireStdUser:async()=>state.auth?{ok:true,requester:{email:state.email}}:{ok:false,response:{status:401}}}
  if(name.includes('stdVideoModels'))return validation
  if(name.includes('stdYoutubeChannelOAuth'))return {protectYoutubeCredentials:encrypt,readYoutubeCredentials:decrypt}
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:{from(){let id;const q={select(){return q},eq(_,value){id=value;return q},async maybeSingle(){return {data:state.rows.get(id)||null}},async upsert(row){state.rows.set(row.key,row);return {error:null}}};return q}}}
  throw Error(name)
 })
 return {state,get:()=>exports.GET({}),post:body=>exports.POST({json:async()=>body})}
}
const model={id:'test',name:'제작 모델',model:'video-v1',endpoint:'https://api.example.test/videos'}
test('model endpoint excludes inline credentials and non HTTPS URLs',()=>{
 for(const endpoint of ['http://host/video','https://key:secret@host/video','https://host/video?key=secret'])assert.throws(()=>validation.validateVideoModel({...model,endpoint}))
 assert.equal(validation.validateVideoModel(model).model,'video-v1')
})
test('catalog masks secrets, preserves blank keys, scopes accounts and applies only existing models',async()=>{
 process.env.VIDEO_MODEL_ENCRYPTION_KEY='fixture-only'
 const f=fixture();f.state.auth=false;assert.equal((await f.get()).status,401);f.state.auth=true
 const saved=await f.post({action:'save',model,api_key:'private-test-secret'})
 assert.equal(saved.status,200);assert.equal(saved.body.models[0].has_key,true)
 assert.ok(!JSON.stringify(saved).includes('private-test-secret'));assert.ok(!JSON.stringify([...f.state.rows.values()]).includes('private-test-secret'))
 assert.equal((await f.post({action:'save',model:{...model,name:'수정'},api_key:''})).status,200)
 assert.equal((await f.post({action:'apply',id:'absent'})).status,400)
 assert.equal((await f.post({action:'apply',id:'test'})).body.active_id,'test')
 f.state.email='two@test.local';assert.deepEqual((await f.get()).body.models,[])
 f.state.email='one@test.local';assert.equal((await f.get()).body.models[0].has_key,true)
 assert.equal((await f.post({action:'delete',id:'test'})).body.active_id,null)
})
