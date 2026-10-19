const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path')
const load=require('./load-ts.cjs'),lib=load(path.resolve('lib/stdMotionVideoProvider.ts')),motion=load(path.resolve('lib/stdMotionStudio.ts'))
test('both automatic modes persist without requiring manual scene keys',()=>{
 for(const mode of ['ae_only','hybrid'])assert.equal(motion.normalizeMotionDraft({version:1,enabled:true,aspect:'9:16',fps:24,scenes:{},automation:{mode,max_ai_clips:1,max_ai_seconds:5}}).automation.mode,mode)
 assert.throws(()=>motion.normalizeMotionDraft({version:1,enabled:true,aspect:'9:16',fps:24,scenes:{},automation:{mode:'unknown',max_ai_clips:1,max_ai_seconds:5}}))
})
test('provider URLs never forward credentials to arbitrary hosts',()=>{
 for(const url of ['https://evil.test/x','https://queue.fal.run.evil.test/x','https://u:p@queue.fal.run/x','http://queue.fal.run/x'])assert.throws(()=>lib.providerUrl(url,'fal'))
 assert.throws(()=>lib.outputVideoUrl({video:{url:'https://evil.test/result.mp4'}}))
})
test('fal and Replicate use authenticated async requests with exact image and duration arguments',async()=>{
 const old=global.fetch,calls=[];global.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.includes('/status')?{status:'COMPLETED'}:url.endsWith('/result')?{video:{url:'https://v.fal.media/out.mp4'}}:url.includes('replicate')?{id:'rep1',urls:{get:'https://api.replicate.com/v1/predictions/rep1'}}:{request_id:'fal1',status_url:'https://queue.fal.run/requests/fal1/status',response_url:'https://queue.fal.run/requests/fal1/result'}}}
 try{
  const config={provider:'fal',endpoint:'https://queue.fal.run/fal-ai/test',image_field:'image_url',duration_field:'duration',duration_type:'string',extra_input:{}}
  const request=await lib.createProviderVideo(config,'fixture-secret',{prompt:'Preserve character',duration:3},'https://storage.test/signed.png')
  assert.equal(JSON.parse(calls[0].options.body).duration,'3');assert.equal(calls[0].options.headers.Authorization,'Key fixture-secret')
  assert.ok(!JSON.stringify(request).includes('fixture-secret'));assert.equal((await lib.pollProviderVideo(config,'fixture-secret',request)).state,'complete')
  await lib.createProviderVideo({...config,provider:'replicate',endpoint:'https://api.replicate.com/v1/models/test/model/predictions',duration_type:'number'},'rep-secret',{prompt:'Still face',duration:4},'https://storage.test/source.png')
  assert.equal(JSON.parse(calls.at(-1).options.body).input.duration,4);assert.equal(calls.at(-1).options.headers.Authorization,'Bearer rep-secret')
 }finally{global.fetch=old}
})
