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
 new Function('exports', 'require', ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(exports, id => {
  if (id.startsWith('@/lib/')) return load(id.slice(6))
  if (id.startsWith('./') && fs.existsSync(path.join(web, 'lib', id + '.ts'))) return load(id.slice(2))
  return localRequire(id)
 })
 return exports
}
async function main() {
 const id = process.argv[2]
 if (!id) throw Error('Usage: node scripts/std_continue_submission.cjs PROJECT_ID [--enqueue]')
 const db = load('supabaseAdmin').supabaseAdmin
 const p = await db.from('std_projects').select('*').eq('id', id).single()
 if (p.error) throw p.error
 if (['approved','canceled'].includes(p.data.status)) throw Error('Project is closed')
 const [s,a] = await Promise.all([
  db.from('std_project_scenes').select('*').eq('project_id',id).order('scene_number'),
  load('stdProjectAssets').loadStdProjectAssets(db, id, '*'),
 ])
 if (s.error || a.error) throw s.error || a.error
 const mouth = load('stdAeMouth')
 const job = mouth.currentAeMouthJob(p.data,s.data,a.data)
 if (!job) throw Error('No submitted AE job matching the current recording and source assets')
 const status = {project_id:id,job_id:job.id,state:job.metadata.state,results:job.metadata.results,render_queue_id:job.metadata.auto_render_queue_id || null}
 if (!process.argv.includes('--enqueue')) { console.log(JSON.stringify(status)); return }
 mouth.reviewedAeMouthAssets(p.data,s.data,a.data)
 if (job.metadata.auto_render_queue_id) { console.log(JSON.stringify(status)); return }
 const claim = await db.from('std_project_assets').update({metadata:{...job.metadata,auto_render_state:'registering'},updated_at:new Date().toISOString()})
  .eq('id',job.id).eq('updated_at',job.updated_at).select('*').maybeSingle()
 if (claim.error || !claim.data) throw Error('Job changed; inspect it again before continuing')
 const queue = await load('stdRenderQueue').enqueueStdProjectRender(id)
 const marked = await db.from('std_project_assets').update({metadata:{...claim.data.metadata,auto_render_state:'queued',auto_render_queue_id:queue.id},updated_at:new Date().toISOString()})
  .eq('id',job.id).eq('updated_at',claim.data.updated_at).select('id').maybeSingle()
 if (marked.error || !marked.data) throw Error('Render is queued but receipt needs recovery; inspect existing queue before retrying')
 console.log(JSON.stringify({project_id:id,render_queue_id:queue.id,render_version:queue.metadata?.render_version,state:'render_queued'}))
}
main().catch(error => { console.error(error.message); process.exitCode=1 })
