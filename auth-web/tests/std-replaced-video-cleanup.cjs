const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('../node_modules/typescript')

const deleted = []
const rows = new Map()
let sharedPath = false
const supabaseAdmin = {
    from(table) {
        assert.equal(table, 'std_project_assets')
        let id = null
        let path = null
        return {
            select() { return this },
            eq(column, value) {
                if (column === 'id') id = value
                if (column === 'metadata->>gcs_path' || column === 'metadata->>storage_path') path = value
                return this
            },
            in() { return this },
            limit() { return Promise.resolve({ data: sharedPath && path ? [{ id: 'shared' }] : [], error: null }) },
            single() { return Promise.resolve({ data: rows.get(id), error: null }) },
        }
    },
}
const source = fs.readFileSync('lib/stdReplacedVideoCleanup.ts', 'utf8')
const moduleExports = {}
new Function('exports', 'require', ts.transpileModule(source, { compilerOptions: { module: 1, target: 7 } }).outputText)(moduleExports, name => {
    if (name === './gcsStorage') return { deleteGcsObject: async ref => deleted.push(ref) }
    if (name === './supabaseAdmin') return { supabaseAdmin }
    throw new Error(name)
})

test('removes old project clip only after replacement is assigned and no live asset uses it', async () => {
    const projectId = 'project-1'
    const old = { id: 'old', metadata: { gcs_bucket: 'bucket', gcs_path: `std-projects/${projectId}/scenes/4/old.mp4` } }
    const replacement = { id: 'new', status: 'assigned', metadata: { gcs_path: `std-projects/${projectId}/scenes/4/new.mp4` } }
    rows.set('old', { status: 'assigned' })
    await moduleExports.cleanupReplacedSceneVideos(projectId, [old], replacement)
    assert.equal(deleted.length, 0)

    rows.set('old', { status: 'replaced' })
    sharedPath = true
    await moduleExports.cleanupReplacedSceneVideos(projectId, [old], replacement)
    assert.equal(deleted.length, 0)

    sharedPath = false
    await moduleExports.cleanupReplacedSceneVideos(projectId, [old], replacement)
    assert.deepEqual(deleted, [{ bucket: 'bucket', objectPath: old.metadata.gcs_path }])

    await moduleExports.cleanupReplacedSceneVideos(projectId, [old], { ...replacement, metadata: { gcs_path: old.metadata.gcs_path } })
    await moduleExports.cleanupReplacedSceneVideos(projectId, [{ ...old, metadata: { ...old.metadata, gcs_path: 'another-project/old.mp4' } }], replacement)
    assert.equal(deleted.length, 1)
    await assert.rejects(moduleExports.cleanupReplacedSceneVideos(projectId, [old], { ...replacement, status: 'replaced' }), /not saved/)
})
