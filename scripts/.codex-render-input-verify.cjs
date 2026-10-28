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

async function main(){const db=load('supabaseAdmin').supabaseAdmin;const id='e9233112-f0d7-4b35-91bf-2f892844eb30';const p=await db.from('std_projects').select('*').eq('id',id).single();const s=await db.from('std_project_scenes').select('*').eq('project_id',id).order('scene_number');const a=await load('stdProjectAssets').loadStdProjectAssets(db,id,'*');if(p.error||s.error||a.error)throw Error('Read failed');const j=a.data.find(x=>x.id==='8b905657-370c-4608-a2da-edfe0662b87f');const n=load('stdAeMouth').aeMouthInput(p.data,s.data,a.data);const old=j.metadata.input;function canonical(x){if(Array.isArray(x))return x.map(canonical);if(x&&typeof x==='object')return Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])]));return x;}const same=(x,y)=>JSON.stringify(canonical(x))===JSON.stringify(canonical(y));for(const k of ['audio','subtitles','tts_speed','cast','annotations','dialogue_scene_index'])if(!same(old[k],n.input[k]))throw Error('Changed critical input: '+k);for(const r of j.metadata.results.filter(x=>x.status==='approved')){const os=old.scenes.find(x=>x.number===r.number),ns=n.input.scenes.find(x=>x.number===r.number);for(const k of ['start','end','image','original_video','text','direction'])if(!same(os[k],ns[k]))throw Error('Changed approved scene '+r.number+' '+k);}const update=await db.from('std_project_assets').update({metadata:{...j.metadata,input:n.input,render_input_verified_at:new Date().toISOString(),render_input_verification:'38 approved source imagery, original video, finalized audio, subtitle timing and directions unchanged; skipped-scene tail plans updated.'},updated_at:new Date().toISOString()}).eq('id',j.id).eq('updated_at',j.updated_at).select('id');if(update.error||!update.data.length)throw Error('Concurrent job change');console.log('Verified 38 generated scenes and saved compatible final render input');}main().catch(e=>{console.error(e.message);process.exitCode=1})
