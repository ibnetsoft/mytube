const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const path = require('node:path')
const source = fs.readFileSync(path.join(__dirname, '../app/api/std/projects/[projectId]/assets/complete/route.ts'), 'utf8')
const compiled = ts.transpile(source, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 })
let updates = 0, currentType = 'thumbnail', currentName = 'final.png'
const project = { id: 'p', status: 'in_progress', project_payload: { script: 'keep', subtitles: [{ text: 'keep' }] } }
const identity = () => ({ script_sha256: 'same' })
const db = { from(table) { return {
  select() { return this }, eq(key) { if (key === 'metadata->>kind') this.claim = true; return this },
  async maybeSingle() { return table === 'std_projects' ? { data: project } : this.claim ? { data: { metadata: { content_identity: { ...identity(), asset_type: currentType, scene_number: null } } } } : { data: null } },
  insert(row) { this.row = row; return this }, async single() { return { data: { id: 'asset', ...this.row, file_name: currentName } } },
  update() { updates++; throw new Error('Project must not be rewritten') },
} } }
const mocks = {
  stdContentIdentity: { projectContentIdentity: identity }, stdComic: { isComicProject: () => false },
  stdAssetEditPolicy: { canEditStdAsset: () => true }, stdSubmittedVideoReplacement: {}, stdReplacedVideoCleanup: {},
  stdAudioMix: { audioAssetStorageFields: type => ({ asset_type: type, metadata: {} }) },
  stdWeb: { requireStdUser: async () => ({ ok: true, requester: { email: 'test', user: { id: 'test' } } }) },
  stdPolicy: {}, stdLegacySync: {},
  gcsStorage: { isGcsConfiguredAsync: async () => true, getGcsObjectMetadata: async () => ({ size: 100, contentType: 'image/png' }) },
  supabaseAdmin: { supabaseAdmin: db },
}
const route = {}
new Function('exports', 'require', compiled)(route, name => name === 'next/server'
  ? { NextResponse: { json: (body, options = {}) => ({ body, status: options.status || 200 }) } }
  : mocks[name.split('/').pop()] || {})
async function run(type, name) {
  currentType = type; currentName = name
  const req = new Request('https://test.invalid', { method: 'POST', body: JSON.stringify({ asset_type: type,
    file_name: name, storage_bucket: 'test', storage_path: 'std-projects/p/file.png' }) })
  return route.POST(req, { params: { projectId: 'p' } })
}
;(async () => {
  for (const [type, name] of [['original', 'thumbnail_background_123.jpg'], ['thumbnail', 'final.png']]) {
    const result = await run(type, name)
    assert.equal(result.status, 200)
    assert.equal(result.body.asset.file_name, name)
  }
  assert.equal(updates, 0, 'thumbnail uploads never rewrite project payload or change subtitle data')
  console.log('PASS: thumbnail background and final uploads return without rewriting project payload')
})().catch(error => { console.error(error); process.exitCode = 1 })
