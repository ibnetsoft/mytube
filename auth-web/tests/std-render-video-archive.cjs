const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('node:path'),vm=require('vm'),ts=require('../node_modules/typescript');
const root=path.resolve(__dirname,'..');
test('recovered video is archived before registration',async()=>{
 let uploaded=false;const exports={};
 const comic={};
 new Function('exports','require',ts.transpile(fs.readFileSync(path.join(root,'lib/stdComic.ts'),'utf8'),{module:1,target:7,esModuleInterop:true}))(comic,()=>require('../public/comic/layouts.json'));
 const db={storage:{from:()=>({download:async()=>({data:{arrayBuffer:async()=>Buffer.from('video')},error:null}),getPublicUrl:()=>({data:{publicUrl:'https://example.test/video'}})})},from:()=>({insert:row=>({select:()=>({single:async()=>{assert.equal(uploaded,true);return {data:{id:'asset',...row},error:null}}})})})};
 vm.runInNewContext(ts.transpile(fs.readFileSync(path.join(root,'lib/stdRenderQueue.ts'),'utf8'),{module:1,target:7}),{exports,Buffer,URL,console,require:name=>{
 if(name==='crypto')return require('crypto');
 if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
 if(name.includes('stdComic'))return comic;
 if(name.includes('stdPolicy'))return {isStdRequiredVideoScene:n=>n<=12,isStdRequiredClipScene:n=>n<=18};
 if(name.includes('stdGeneratedSceneStorage')){const helper={};new Function('exports','require',ts.transpile(fs.readFileSync(path.join(root,'lib/stdGeneratedSceneStorage.ts'),'utf8'),{module:1,target:7}))(helper,require);return helper;}
 if(name.includes('gcsStorage'))return {gcsBucketName:()=> 'render',uploadGcsBuffer:async args=>{assert.equal((args.data||args.buffer).toString(),'video');uploaded=true;return {bucket:'render',path:args.objectPath}},isGcsConfiguredAsync:async()=>true};
 return {};
 }});
 const rows=await exports.ensureStdGeneratedSceneAssetsArchived({id:'project'},[{id:'scene',scene_number:1,metadata:{video_storage_bucket:'source',video_storage_path:'video.mp4'}}],[]);
 assert.equal(rows.length,1);assert.equal(rows[0].metadata.gcs_bucket,'render');assert.equal(rows[0].metadata.gcs_path,'video.mp4');
});
