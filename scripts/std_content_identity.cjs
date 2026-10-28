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

async function main() {
 const id=process.argv[2], record=process.argv.includes('--record')
 if(!id)throw Error('Usage: node scripts/std_content_identity.cjs PROJECT_ID [--record]')
 const db=load('supabaseAdmin').supabaseAdmin, identity=load('stdContentIdentity')
 const p=await db.from('std_projects').select('*').eq('id',id).single();if(p.error)throw p.error
 const project=p.data,assets=[]
 for(let start=0;;start+=500){const page=await db.from('std_project_assets').select('*').eq('project_id',id).order('id').range(start,start+499);if(page.error)throw page.error;assets.push(...page.data);if(page.data.length<500)break}
 const pending=[]
 const byId=new Map(assets.map(a=>[a.id,a])),report={project_id:id,topic_queue_id:project.topic_queue_id,current:identity.projectContentIdentity(project),recorded:0,legacy_unversioned:[],conflicts:[],audio_versions:[]}
 const directory=path.join(root,'output','content-identity',id);fs.mkdirSync(directory,{recursive:true})
 if(record)fs.writeFileSync(path.join(directory,`before-${Date.now()}.json`),JSON.stringify({project,assets},null,2))
 function audioIdentity(a){const rows=a.metadata?.subtitle_timeline;if(!rows?.length)return null;const sha=identity.contentHash(rows.map(r=>identity.speechText(r.text)).join(''));return {...identity.projectContentIdentity(project),asset_type:'audio',script_sha256:sha,script_revision:`sha256:${sha}`,subtitle_text_sha256:sha,timeline_sha256:identity.contentHash(identity.timelineRows(rows)),basis:'legacy_recorded_timeline',parent_asset_ids:[],audio_asset_id:a.id}}
 for(const a of assets){
  try{identity.assertAssetScope(project,a)}catch(e){report.conflicts.push({asset_id:a.id,error:e.message});continue}
  if(a.asset_type==='audio'&&a.metadata?.subtitle_timeline?.length)report.audio_versions.push({asset_id:a.id,status:a.status,duration_seconds:a.metadata.subtitle_timeline.at(-1).end,script_sha256:audioIdentity(a).script_sha256})
  if(a.metadata?.content_identity){if(a.metadata.content_identity.basis==='legacy_database_scope')report.legacy_unversioned.push(a.id);continue}
  if(['processing','rendering'].includes(a.metadata?.state))continue
  const sourceAudio=byId.get(a.metadata?.source_audio_id),recording=sourceAudio&&audioIdentity(sourceAudio)
  const own=audioIdentity(a)
  const proof=own||recording
  const receipt=proof?{...proof,asset_type:a.asset_type,scene_number:a.scene_number||null,scene_id:a.scene_id||null,
    parent_asset_ids:recording?[sourceAudio.id,a.metadata?.source_image_id,a.metadata?.source_video_id].filter(Boolean):[],
    audio_asset_id:recording?sourceAudio.id:a.id,generation_job_id:a.metadata?.ae_mouth_fingerprint||null}:
   {...identity.projectContentIdentity(project),asset_type:a.asset_type,scene_number:a.scene_number||null,scene_id:a.scene_id||null,
    script_revision:null,script_sha256:null,subtitle_text_sha256:null,visual_sha256:null,basis:'legacy_database_scope',parent_asset_ids:[]}
  if(!proof)report.legacy_unversioned.push(a.id)
  if(record){pending.push(async()=>{let q=db.from('std_project_assets').update({metadata:{...a.metadata,content_identity:receipt},updated_at:new Date().toISOString()}).eq('id',a.id).eq('project_id',id)
   q=a.updated_at?q.eq('updated_at',a.updated_at):q.is('updated_at',null)
   const result=await q.select('id').maybeSingle();if(result.error)throw result.error;if(!result.data)throw Error(`Asset changed during audit: ${a.id}`);report.recorded++})}
 }
 for(let i=0;i<pending.length;i+=4){const batch=await Promise.allSettled(pending.slice(i,i+4).map(fn=>fn()));const failures=batch.filter(r=>r.status==='rejected');if(failures.length)throw failures[0].reason;if(i%100===0)console.error(`Identity records ${Math.min(i+4,pending.length)}/${pending.length}`)}
 const audio=identity.selectNarrationAsset(project,assets)
 report.narration=identity.assertNarrationIdentity(project,audio,project.project_payload.subtitles)
 if(record){for(const a of assets.filter(a=>a.asset_type==='audio'&&a.metadata?.subtitle_timeline?.length)){await identity.persistContentRevision(db,{...project,project_payload:{script:a.metadata.subtitle_timeline.map(r=>r.text||'').join(''),subtitles:a.metadata.subtitle_timeline,subtitle_source_audio_id:a.id,structure:{}}})}
  await identity.persistContentRevision(db,project)
  const payload=identity.bindProjectContent(project,{...project.project_payload,subtitle_source_audio_id:audio.id})
  const saved=await db.from('std_projects').update({project_payload:payload,updated_at:new Date().toISOString()}).eq('id',id).eq('updated_at',project.updated_at).select('id').maybeSingle()
  if(saved.error||!saved.data)throw saved.error||Error('Project changed during audit; assets preserved but project receipt not updated')}
 fs.writeFileSync(path.join(directory,'audit.json'),JSON.stringify(report,null,2))
 console.log(JSON.stringify({project_id:id,recorded:report.recorded,legacy_unversioned:report.legacy_unversioned.length,conflicts:report.conflicts,narration:report.narration,audio_versions:report.audio_versions,report:path.join(directory,'audit.json')}))
 if(report.conflicts.length)process.exitCode=1
}
main().catch(e=>{console.error(e.message);process.exitCode=1})
