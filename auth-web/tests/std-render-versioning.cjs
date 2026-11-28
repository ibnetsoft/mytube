const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const ts = require('typescript')

function load(relative) {
    const filename = path.resolve(__dirname, '..', relative)
    const mod = new Module(filename, module)
    mod.filename = filename
    mod.paths = Module._nodeModulePaths(path.dirname(filename))
    mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    }).outputText, filename)
    return mod.exports
}

const { normalizeStdRenderHistory, nextStdRenderVersion, attachStdRenderPlaybackAssets } = load('lib/stdRenderVersion.ts')

const legacyRows = [
    { id: 'newer', metadata: { std_web_project_id: 'project-1' } },
    { id: 'older', metadata: { std_web_project_id: 'project-1' } },
]
assert.deepEqual(normalizeStdRenderHistory(legacyRows).map(row => row.render_version), [2, 1])
assert.equal(nextStdRenderVersion(legacyRows), 3)

const versionedRows = [
    { id: 'v3', metadata: { render_version: 3 } },
    { id: 'v1', metadata: { render_version: 1 } },
]
assert.equal(nextStdRenderVersion(versionedRows), 4)
assert.equal(nextStdRenderVersion([]), 1)

const storage = { gcs_bucket: 'private', gcs_path: 'final/verified.mp4', sha256: 'a'.repeat(64) }
const completed = { status: 'completed', result_file_id: 'gs://private/final/verified.mp4', metadata: storage }
const final = { id: 'owned-final', status: 'uploaded', asset_type: 'video', metadata: { ...storage, kind: 'motion_final' } }
assert.deepEqual(attachStdRenderPlaybackAssets([completed, { ...completed, status: 'rendering' }], [final])
    .map(row => row.playback_asset_id), ['owned-final', null])
assert.equal(attachStdRenderPlaybackAssets([completed], [{ ...final, metadata: { ...final.metadata, sha256: 'b'.repeat(64) } }])[0].playback_asset_id, null)
assert.equal(attachStdRenderPlaybackAssets([completed], [{ ...final, status: 'deleted' }])[0].playback_asset_id, null)

console.log('PASS: stable render versions and exact saved-final playback asset matching')
