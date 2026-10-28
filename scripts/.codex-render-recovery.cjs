const fs = require('node:fs'), path = require('node:path'), { createRequire } = require('node:module')
const root = path.resolve(__dirname, '..'), web = path.join(root, 'auth-web')
const req = createRequire(path.join(web, 'package.json'))
const envFile = path.join(root, '.env')
if (fs.existsSync(envFile)) process.loadEnvFile(envFile)
const ts = req('typescript'), cache = new Map()
function load(name) {
 if (cache.has(name)) return cache.get(name)
 const exports = {}; cache.set(name, exports)
 const file = path.join(web, 'lib', name + '.ts'), localRequire = createRequire(file)
 new Function('exports', 'require', ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText)(exports, id => {
  if (id.startsWith('@/lib/')) return load(id.slice(6))
  if (id.startsWith('./') && fs.existsSync(path.join(web, 'lib', id + '.ts'))) return load(id.slice(2))
  return localRequire(id)
 })
 return exports
}

async function main(){const id='e9233112-f0d7-4b35-91bf-2f892844eb30';const db=load('supabaseAdmin').supabaseAdmin;const p=await db.from('std_projects').select('project_payload').eq('id',id).single();if(p.error)throw p.error;const recovery=p.data.project_payload.content_recovery;if(recovery?.expected_duration_seconds!==827.1430204081636||p.data.project_payload.subtitles.length!==281)throw Error('Original recovery invariant failed');const q=await load('stdRenderQueue').enqueueStdProjectRender(id);console.log(JSON.stringify({queue_id:q.id,status:q.status,version:q.metadata?.render_version,expected_duration:recovery.expected_duration_seconds}));}main().catch(e=>{console.error(e.message);process.exitCode=1})
