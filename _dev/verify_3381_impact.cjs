const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')
const root = path.resolve(__dirname, '..')
const web = path.join(root, 'auth-web')
if (fs.existsSync(path.join(root, '.env'))) process.loadEnvFile(path.join(root, '.env'))
const req = createRequire(path.join(web, 'package.json'))
const ts = req('typescript')
const cache = new Map()
function load(name) {
  if (cache.has(name)) return cache.get(name)
  const exports = {}
  cache.set(name, exports)
  const file = path.join(web, 'lib', `${name}.ts`)
  const localRequire = createRequire(file)
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText
  new Function('exports', 'require', source)(exports, id => {
    if (id.startsWith('@/lib/')) return load(id.slice(6))
    if (id.startsWith('./') && fs.existsSync(path.join(web, 'lib', `${id}.ts`))) return load(id.slice(2))
    return localRequire(id)
  })
  return exports
}
async function main() {
  const id = '6b46f709-b4bf-4ccd-ac12-9c8c3981e249'
  const db = load('supabaseAdmin').supabaseAdmin
  const { data, error } = await db.from('std_projects').select('status,submitted_at,project_payload').eq('id', id).single()
  if (error) throw error
  const scenes = data.project_payload?.structure?.scenes || []
  const results = scenes.filter(s => Number(s.scene_number ?? s.sceneNumber) >= 19 && Number(s.scene_number ?? s.sceneNumber) <= 41).map(s => {
    const n = Number(s.scene_number ?? s.sceneNumber)
    const asset = s.metadata?.ae_effect_asset || s.ae_effect_asset || {}
    const plan = s.ae_effect_plan || s.metadata?.ae_effect_plan || {}
    const bubbles = plan.speech_bubbles?.bubbles || []
    return { scene: n, status: asset.status, preset: asset.preset || plan.preset, gcs: asset.gcs_path || asset.object_path, url: s.ae_video_url || asset.media_url, bubble: bubbles[0]?.text || '', sourceVideo: Boolean(asset.source_video_sha256 || asset.source_image?.object_path?.endsWith('.mp4')), quality: asset.quality_report?.passed }
  }).sort((a,b) => a.scene-b.scene)
  const mouth = new Set([25,29,31,32,33,34,36,39,40,41])
  const summary = {
    projectStatus: data.status,
    submittedAt: data.submitted_at,
    count: results.length,
    ready: results.filter(r => r.status === 'ready' && r.gcs && r.url).length,
    presetOk: results.filter(r => r.preset === 'webtoon_impact_beat_v1').length,
    mouthCount: results.filter(r => mouth.has(r.scene) && r.bubble && r.sourceVideo && r.quality).length,
    failures: results.filter(r => !(r.status === 'ready' && r.gcs && r.url && r.preset === 'webtoon_impact_beat_v1') || (mouth.has(r.scene) && !(r.bubble && r.sourceVideo && r.quality))),
    results
  }
  console.log(JSON.stringify(summary, null, 2))
  if (summary.ready !== 23 || summary.presetOk !== 23 || summary.mouthCount !== 10) process.exitCode = 2
}
main().catch(e => { console.error(e); process.exit(1) })
