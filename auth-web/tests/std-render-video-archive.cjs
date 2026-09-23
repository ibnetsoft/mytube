const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm'),ts=require('../node_modules/typescript');
test('recovered video is archived before registration',async()=>{
 let uploaded=false;const exports={};
 const comic={};
 new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdComic.ts','utf8'),{module:1,target:7,esModuleInterop:true}))(comic,()=>require('../public/comic/layouts.json'));
 const db={storage:{from:()=>({download:async()=>({data:{arrayBuffer:async()=>Buffer.from('video')},error:null}),getPublicUrl:()=>({data:{publicUrl:'https://example.test/video'}})})},from:()=>({insert:row=>({select:()=>({single:async()=>{assert.equal(uploaded,true);return {data:{id:'asset',...row},error:null}}})})})};
 vm.runInNewContext(ts.transpile(fs.readFileSync('lib/stdRenderQueue.ts','utf8'),{module:1,target:7}),{exports,Buffer,console,require:name=>{
 if(name==='crypto')return require('crypto');
 if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
 if(name.includes('stdComic'))return comic;
 if(name.includes('stdPolicy'))return {isStdRequiredVideoScene:n=>n<=12};
 if(name.includes('gcsStorage'))return {uploadGcsBuffer:async args=>{assert.equal(args.data.toString(),'video');uploaded=true;return {bucket:'render',path:args.objectPath}},isGcsConfiguredAsync:async()=>true};
 return {};
 }});
 const rows=await exports.ensureStdGeneratedSceneAssetsArchived({id:'project'},[{id:'scene',scene_number:1,metadata:{video_storage_bucket:'source',video_storage_path:'video.mp4'}}],[]);
 assert.equal(rows.length,1);assert.equal(rows[0].metadata.gcs_bucket,'render');assert.equal(rows[0].metadata.gcs_path,'video.mp4');
});
