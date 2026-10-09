const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const ts = require('typescript')
const filename = path.resolve(__dirname, '../lib/stdProjectAssets.ts')
const mod = new Module(filename, module)
mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, filename)
const { loadStdProjectAssets } = mod.exports
function database(rows, failAt = -1) {
    const pages = []
    return { pages, from(table) {
        assert.equal(table, 'std_project_assets')
        const orders = []
        return {
            select(columns) { assert.equal(columns, '*'); return this },
            eq(key, value) { assert.equal(key, 'project_id'); assert.equal(value, 'project'); return this },
            in(key, values) { assert.equal(key, 'status'); assert.deepEqual(values, ['uploaded', 'assigned']); return this },
            order(key) { orders.push(key); return this },
            async range(start, end) {
                assert.deepEqual(orders, ['created_at', 'id'])
                assert.equal(end - start, 499)
                pages.push([start, end])
                return start === failAt ? { error: { message: 'query failed' } } : { data: rows.slice(start, end + 1), error: null }
            },
        }
    } }
}
test('all 1265 assets load, including 18 original clips after the first 1000 rows', async () => {
    const rows = Array.from({ length: 1265 }, (_, i) => ({ id: i, asset_type: i >= 1018 && i < 1036 ? 'video' : 'audio' }))
    const db = database(rows)
    const result = await loadStdProjectAssets(db, 'project', '*')
    assert.equal(result.error, null)
    assert.deepEqual(result.data, rows)
    assert.equal(result.data.filter(a => a.asset_type === 'video').length, 18)
    assert.deepEqual(db.pages, [[0,499], [500,999], [1000,1499]])
})
test('exact page boundary terminates on an empty next page', async () => {
    const db = database(Array.from({length:500}, (_,id)=>({id})))
    assert.equal((await loadStdProjectAssets(db, 'project', '*')).data.length, 500)
    assert.equal(db.pages.length, 2)
})
test('a later-page failure never returns a silently incomplete project', async () => {
    const result = await loadStdProjectAssets(database(Array(1265).fill({}), 1000), 'project', '*')
    assert.equal(result.data, null)
    assert.equal(result.error.message, 'query failed')
})

test('project asset enrichment does not wait for private media signing', () => {
    const route = fs.readFileSync(path.resolve(__dirname, '../app/api/std/projects/[projectId]/route.ts'), 'utf8')
    const ast = ts.createSourceFile('route.ts', route, ts.ScriptTarget.Latest, true)
    let initializer
    function visit(node) {
        if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'enrichedAssets') initializer = node.initializer
        ts.forEachChild(node, visit)
    }
    visit(ast)
    assert(initializer)
    const code = ts.transpileModule(`return (${initializer.getText(ast)})`, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
    const assets = Array.from({ length: 1265 }, (_, id) => ({ id, metadata: { gcs_path: `private/${id}` } }))
    const enriched = new Function('assets', 'CONTENT_ASSETS_BUCKET', 'storagePublicUrl', code)(assets, 'content-assets', () => '')
    assert(Array.isArray(enriched), 'Project data must be immediately available without signing every file')
    assert.equal(enriched.length, assets.length)
    assert.deepEqual(enriched[1264], assets[1264])
})
