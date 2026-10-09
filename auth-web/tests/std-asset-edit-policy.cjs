const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript')
const source=fs.readFileSync('lib/stdAssetEditPolicy.ts','utf8'),moduleExports={}
new Function('exports','require',ts.transpileModule(source,{compilerOptions:{module:1,target:7}}).outputText)(moduleExports,name=>{
 if(name==='./stdComic')return{isComicProject:p=>p.project_payload?.comic===true}
 if(name==='./stdPolicy')return{isStdRequiredClipScene:n=>Number(n)>=1&&Number(n)<=18}
 throw Error(name)
})
const can=moduleExports.canEditStdAsset
test('submitted project accepts replacement of scenes 1–18 only',()=>{
 const p={status:'review_requested',project_payload:{}}
 assert.equal(can(p,'video',4),true)
 assert.equal(can(p,'video',18),true)
 for(const [type,scene] of [['video',19],['image',4],['thumbnail',null],['video',null]])assert.equal(can(p,type,scene),false)
 assert.equal(can(p,'sfx',null),true)
 assert.equal(can(p,'bgm',null),true)
 assert.equal(can(p,'sfx',4),false)
 assert.equal(can({...p,project_payload:{comic:true}},'video',4),false)
 assert.equal(can({...p,status:'approved'},'video',4),false)
 assert.equal(can({...p,status:'in_progress'},'video',4),true)
})
