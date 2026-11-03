const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript')
const load=require('./load-ts-module.cjs'),identity=load('lib/stdContentIdentity.ts'),policy=load('lib/stdPolicy.ts')
for(const route of ['upload','complete']) test(`${route} readiness ignores old assets and requires selected clips`,async()=>{
 const file=fs.readFileSync(path.resolve(__dirname,`../app/api/std/projects/[projectId]/assets/${route}/route.ts`),'utf8')
 const ast=ts.createSourceFile('route.ts',file,ts.ScriptTarget.Latest,true)
 const fn=ast.statements.find(s=>ts.isFunctionDeclaration(s)&&s.name?.text==='updateSceneAssetStatus');assert(fn)
 const code=ts.transpileModule(`${fn.getText(ast)}\nreturn updateSceneAssetStatus`,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
 let assets=[],written
 const db={from(table){const q={select(){return q},eq(){return q},in(){return q},update(v){written=v;return q},then(resolve,reject){return Promise.resolve({data:table==='std_project_assets'?assets:[],error:null}).then(resolve,reject)}};return q}}
 const run=new Function('supabaseAdmin','assetMatchesContentRevision','isStdVideoPromptScene','isStdRequiredClipScene',code)(db,identity.assetMatchesContentRevision,policy.isStdVideoPromptScene,policy.isStdRequiredClipScene)
 const project={id:'p',topic_queue_id:1,project_payload:{script:'new',strict_content_identity:true,structure:{required_video_scene_count:18,motion_graphic_video_scenes:[19,60,70]}}}
 const current=identity.projectContentIdentity(project).script_sha256
 assets=[{asset_type:'video',metadata:{content_identity:{script_sha256:'old'}}},{asset_type:'image',metadata:{content_identity:{script_sha256:current}}}]
 await run('p',19,project);assert.equal(written.asset_status,'missing')
 await run('p',20,project);assert.equal(written.asset_status,'ready')
 assets.push({asset_type:'video',metadata:{content_identity:{script_sha256:current}}})
 await run('p',19,project);assert.equal(written.asset_status,'ready')
})
