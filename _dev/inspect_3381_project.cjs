const fs = require('node:fs'), path = require('node:path'), { createRequire } = require('node:module')
const root = path.resolve(__dirname, '..'), web = path.join(root, 'auth-web')
if (fs.existsSync(path.join(root, '.env'))) process.loadEnvFile(path.join(root, '.env'))
const req = createRequire(path.join(web, 'package.json')), ts = req('typescript'), cache = new Map()
function load(name) {
  if (cache.has(name)) return cache.get(name)
  const exports = {}; cache.set(name, exports)
  const file = path.join(web, 'lib', name + '.ts'), localRequire = createRequire(file)
  new Function('exports','require',ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText)(exports,id=>{
    if(id.startsWith('@/lib/')) return load(id.slice(6))
    if(id.startsWith('./') && fs.existsSync(path.join(web,'lib',id+'.ts'))) return load(id.slice(2))
    return localRequire(id)
  }); return exports
}
async function main(){
  const id='6b46f709-b4bf-4ccd-ac12-9c8c3981e249', db=load('supabaseAdmin').supabaseAdmin
  const [p,s,a]=await Promise.all([
    db.from('std_projects').select('*').eq('id',id).single(),
    db.from('std_project_scenes').select('*').eq('project_id',id).order('scene_number'),
    load('stdProjectAssets').loadStdProjectAssets(db,id,'*')
  ])
  if(p.error||s.error||a.error) throw p.error||s.error||a.error
  const wanted=new Set([25,29,31,32,33,34,36,39,40,41])
  const subs=(p.data.project_payload?.subtitles||[]).filter(x=>wanted.has(Number(x.scene_number??x.scene??x.sceneNumber)))
  console.log(JSON.stringify({project:{id:p.data.id,status:p.data.status,title:p.data.title,topic_queue_id:p.data.topic_queue_id,payload_keys:Object.keys(p.data.project_payload||{}),mouth_work_policy:p.data.project_payload?.mouth_work_policy},scenes:(s.data||[]).filter(x=>wanted.has(Number(x.scene_number))).map(x=>({id:x.id,scene_number:x.scene_number,image_url:x.image_url,metadata:x.metadata})),assets:(a.data||[]).map(x=>({id:x.id,scene_number:x.scene_number,asset_type:x.asset_type,status:x.status,file_name:x.file_name,metadata:x.metadata})),subtitles:subs},null,2))
}
main().catch(e=>{console.error(e);process.exit(1)})
