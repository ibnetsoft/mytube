const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript'),sharp=require('sharp')
function load(file,mocks={}){const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:1,target:9,esModuleInterop:true}}).outputText)(ex,n=>mocks[n]||require(n));return ex}
test('template bitmap is saved in GCS and database settings contain only its reference',async()=>{
 const bytes=await sharp({create:{width:10,height:10,channels:4,background:{r:0,g:0,b:0,alpha:0}}}).png().toBuffer()
 let saved
 const storage={isGcsConfiguredAsync:async()=>true,gcsBucketName:()=> 'bucket',uploadGcsBuffer:async input=>{saved=input;return{bucket:'bucket',path:input.objectPath}},downloadGcsObject:async ref=>{assert.equal(ref.bucket,'bucket');assert.equal(ref.objectPath,saved.objectPath);return bytes}}
 const lib=load('lib/stdTemplateOverlayPng.ts',{'./gcsStorage':storage})
 const settings={std_image_template_enabled:true,std_template_text_layers:[{text:'test'}],std_template_overlay_layers:[{text:'test'}],std_template_overlay_png_data_url:'data:image/png;base64,'+bytes.toString('base64')}
 const persisted=await lib.persistTemplateOverlay('project',settings)
 assert.equal(persisted.std_template_overlay_png_data_url,null);assert.match(saved.objectPath,/^std-projects\/project\/template-overlay\/[a-f0-9]{64}\.png$/)
 assert.deepEqual(await lib.templateOverlayPng(persisted),bytes)
 await assert.rejects(()=>lib.persistTemplateOverlay('different-project',persisted),/Invalid/)
 storage.uploadGcsBuffer=async()=>{throw Error('GCS unavailable')}
 await assert.rejects(()=>lib.persistTemplateOverlay('project',settings),/GCS unavailable/)
})
test('status read fails explicitly instead of falling back to full project downloads',async()=>{
 const lib=load('lib/stdProjectStatusContext.ts')
 const db={rpc:async(name,args)=>{assert.equal(name,'std_project_status_context');assert.deepEqual(args.p_project_ids,['p']);return{error:Error('RPC unavailable')}},from:()=>assert.fail('No full table fallback')}
 await assert.rejects(()=>lib.loadStdProjectStatusContext(db,['p']),/RPC unavailable/)
})
