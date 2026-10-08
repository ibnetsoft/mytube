const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), path = require('path'), ts = require('typescript')
const root = path.resolve(__dirname, '..')
function load(file, deps = {}) {
 const exports = {}
 new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), { compilerOptions: { module: 1, target: 9 } }).outputText)(exports, name => {
  if (name in deps) return deps[name]
  throw Error('Unexpected dependency: ' + name)
 })
 return exports
}
const helpers = load('lib/renderQueuePublishMetadata.ts')
const task = { id: 'queue', project_id: 1000003373, project_name: 'Old queue title', metadata: { std_web_project_id: 'web', topic_queue_id: 3373 } }
const project = { id: 'web', topic_queue_id: 3373, title: 'Project title', project_payload: { script: 'preserve', publish_metadata: { title: '日本語のタイトル', description: '保存された説明', tags: ['朗読', '江戸'] } } }
function harness(authorized = true) {
 const rows = { remote_render_queue: structuredClone(task), std_projects: structuredClone(project), topics_queue: { id: 3373, publish_metadata: { description: 'Old topic description' } } }
 const db = { from(table) {
  let patch
  const q = { select: () => q, eq: () => q, update: value => { patch = value; return q }, single: () => q, maybeSingle: () => q,
   then: (a, b) => { if (patch) Object.assign(rows[table], patch); return Promise.resolve({ data: rows[table], error: null }).then(a, b) } }
  return q
 } }
 const route = load('app/api/admin/render-queue/metadata/route.ts', {
  '@supabase/supabase-js': { createClient: () => db }, 'next/server': { NextResponse: { json: (body, init) => Response.json(body, init) } },
  '../../_auth': { requireSuperAdmin: async () => authorized ? { user: {} } : Response.json({ error: 'Forbidden' }, { status: 403 }), isAuthResponse: value => value instanceof Response },
  '@/lib/renderQueuePublishMetadata': helpers,
  '@/lib/googleDrive': { getDriveFileJson: async () => { throw Error('GCS projects must not require Drive') }, updateDriveFileJson: async () => { throw Error('Unexpected Drive write') } },
 })
 return { rows, route }
}
test('3373-style GCS task reads title, description and tags from its linked web project', async () => {
 const { route } = harness()
 const res = await route.GET(new Request('https://test/metadata?id=queue'))
 const value = await res.json()
 assert.equal(res.status, 200)
 assert.equal(value.title, project.project_payload.publish_metadata.title)
 assert.equal(value.description, '保存された説明')
 assert.deepEqual(value.tags, ['朗読', '江戸'])
})
test('edits save without a Drive folder, preserve project data and survive reopening', async () => {
 const { route, rows } = harness()
 const next = { title: 'Edited', description: '', tags: [] }
 const res = await route.PATCH(new Request('https://test/metadata?id=queue', { method: 'PATCH', body: JSON.stringify(next) }))
 assert.equal(res.status, 200)
 assert.equal(rows.std_projects.project_payload.script, 'preserve')
 assert.deepEqual(rows.std_projects.project_payload.publish_metadata, next)
 assert.deepEqual(rows.remote_render_queue.metadata.publish_metadata, next)
 const reopened = await (await route.GET(new Request('https://test/metadata?id=queue'))).json()
 for (const key of Object.keys(next)) assert.deepEqual(reopened[key], next[key])
})
test('legacy metadata and titles arrays are supported; explicit admin edits take priority', () => {
 assert.equal(helpers.resolveRenderPublishMetadata(task, null, { publish_metadata: { titles: ['Candidate title'] } }).title, 'Candidate title')
 assert.equal(helpers.resolveRenderPublishMetadata(task, project, null, { description: 'Legacy edit' }).description, 'Legacy edit')
 assert.deepEqual(helpers.resolveRenderPublishMetadata({ ...task, metadata: { publish_metadata: { tags: [] } } }, project).tags, [])
})
test('unauthorized requests cannot read or write and invalid tags are rejected', async () => {
 const denied = harness(false)
 assert.equal((await denied.route.GET(new Request('https://test/metadata?id=queue'))).status, 403)
 assert.equal((await denied.route.PATCH(new Request('https://test/metadata?id=queue', { method: 'PATCH', body: '{}' }))).status, 403)
 const { route } = harness()
 assert.equal((await route.PATCH(new Request('https://test/metadata?id=queue', { method: 'PATCH', body: JSON.stringify({ tags: [1] }) }))).status, 400)
})
