const test = require('node:test'), assert = require('node:assert/strict')
const load = require('./load-ts.cjs'), path = require('node:path')
const { attachStdProjectCategories } = load(path.join(__dirname, '../lib/stdProjectCategories.ts'))

test('Japanese projects retain their saved genres regardless of title or language', async () => {
    const db = { from(table) {
        assert.equal(table, 'categories')
        return { select(columns) {
            assert.equal(columns, 'id,name')
            return { async in(key, ids) {
                assert.equal(key, 'id'); assert.deepEqual(ids, [13, 14, 15, 2, 999])
                return { data: [{ id: 13, name: '日本昔話' }, { id: 14, name: '다큐멘터리' }, { id: 15, name: '일본사건' }, { id: 2, name: '옛날이야기' }] }
            } }
        } }
    } }
    const rows = [13, 13, 14, 15, 2, 999, null].map((category_id, id) => ({ id, category_id, language: 'ja', title: '日本語の動画' }))
    const result = await attachStdProjectCategories(db, rows)
    assert.deepEqual(result.map(row => row.category_name), ['日本昔話', '日本昔話', '다큐멘터리', '일본사건', '옛날이야기', null, null])
    assert.equal(rows[0].category_name, undefined)
})

test('missing categories never invent a genre and lookup errors propagate', async () => {
    assert.deepEqual(await attachStdProjectCategories({ from: () => assert.fail() }, [{ id: 'p' }]), [{ id: 'p', category_name: null }])
    await assert.rejects(() => attachStdProjectCategories({ from: () => ({ select: () => ({ in: async () => ({ error: new Error('unavailable') }) }) }) }, [{ category_id: 13 }]), /unavailable/)
})
