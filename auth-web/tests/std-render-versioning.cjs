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

const { normalizeStdRenderHistory, nextStdRenderVersion } = load('lib/stdRenderVersion.ts')

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

console.log('PASS: legacy renders receive stable versions and subsequent renders increment in place')
