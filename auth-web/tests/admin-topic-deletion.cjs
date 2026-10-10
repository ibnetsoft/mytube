const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

function loadTs(file, dependencies = {}) {
    const exports = {}
    const source = fs.readFileSync(path.join(__dirname, '..', file), 'utf8')
    new Function('exports', 'require', ts.transpile(source, { module: 1, target: 7 }))(
        exports, name => { if (!(name in dependencies)) throw new Error(`Unexpected import ${name}`); return dependencies[name] },
    )
    return exports
}
const lib = loadTs('lib/adminTopicDeletion.ts')
const categories = [
    { id: 1, name: '한국 롱폼', language: 'ko' },
    { id: 2, name: '한국 쇼츠', language: null, video_type: 'shorts' },
    { id: 3, name: '일본', language: 'ja' },
]
function database(rows, options = {}) {
    const tables = {
        categories: structuredClone(categories), topics_queue: structuredClone(rows),
        std_projects: options.projects || [], remote_hermes_queue: options.jobs || [],
        script_worker_jobs: options.scriptJobs || [],
    }
    const calls = []
    return {
        tables, calls,
        from(table) {
            const q = { table, filters: [], deletion: false, from: 0, to: Infinity }
            const query = {
                select(fields, options) { q.select = fields; q.count = options?.count; return query },
                eq(field, value) { q.filters.push(row => row[field] === value); return query },
                in(field, values) { q.filters.push(row => values.map(String).includes(String(row[field]))); return query },
                is(field, value) { q.filters.push(row => (row[field] ?? null) === value); return query },
                not(field, _operator, values) { const excluded = values.slice(1, -1).split(','); q.filters.push(row => !excluded.includes(row[field])); return query },
                or(expression) {
                    const ids = expression.match(/\(([^)]+)\)/)[1].split(',')
                    q.filters.push(row => ids.includes(String(row.topic_queue_id)) || ids.includes(String(row.topic_id)))
                    return query
                },
                order(field, options) { q.order = [field, options.ascending]; return query },
                range(from, to) { q.from = from; q.to = to; return query },
                delete() { q.deletion = true; return query },
                async then(resolve, reject) {
                    try {
                        calls.push(q)
                        if (options.errorTable === table || (q.deletion && options.deleteError)) {
                            return resolve({ data: null, error: { message: 'fixture lookup failure' } })
                        }
                        if (q.deletion && options.beforeDelete) options.beforeDelete(tables)
                        let result = tables[table].filter(row => q.filters.every(filter => filter(row)))
                        const count = result.length
                        if (q.order) result.sort((a, b) => (Number(a[q.order[0]]) - Number(b[q.order[0]])) * (q.order[1] ? 1 : -1))
                        result = result.slice(q.from, q.to + 1)
                        if (q.deletion) {
                            tables[table] = tables[table].filter(row => !result.includes(row))
                        }
                        resolve({ data: structuredClone(result), count, error: null })
                    } catch (error) { reject(error) }
                },
            }
            return query
        },
    }
}
const topic = (id, fields = {}) => ({ id, topic: `주제 ${id}`, category_id: 1, status: 'pending', assigned_at: null, ...fields })

test('IDs reject invalid and broad requests while preserving bigint precision', () => {
    for (const invalid of [undefined, [], ['1 OR 1=1'], ['0'], [-1], [1.5], ['01'], Array(501).fill('1'), ['9223372036854775808'], [Number.MAX_SAFE_INTEGER + 1]]) {
        assert.throws(() => lib.topicDeletionIds(invalid), lib.TopicDeletionInputError)
    }
    assert.deepEqual(lib.topicDeletionIds([1, '1', '9223372036854775807']), ['1', '9223372036854775807'])
    assert.throws(() => lib.topicDeletionLanguage('all'), lib.TopicDeletionInputError)
})

test('list includes hidden and unprepared topics across Korean categories, with accurate pagination', async () => {
    const db = database([
        topic(1, { status: 'excluded', progress_payload: { admin_hidden: true } }),
        topic(2, { category_id: 2, pregenerated_script_status: 'pending' }),
        topic(3, { category_id: 3 }), topic(4, { status: 'assigned' }),
    ])
    const first = await lib.listTopicsForDeletion(db, 'ko', 1, 1)
    assert.equal(first.total, 2)
    assert.equal(first.hasMore, true)
    assert.equal(first.topics[0].id, '2')
    assert.equal(first.topics[0].video_type, 'shorts')
    const second = await lib.listTopicsForDeletion(db, 'ko', 2, 1)
    assert.equal(second.hasMore, false)
    assert.equal(second.topics[0].id, '1')
    assert.equal(second.topics[0].video_type, 'longform')
    assert.equal(second.topics[0].status, 'excluded')
})

test('list exposes project and generation protection before user selects', async () => {
    const db = database([topic(1), topic(2)], {
        projects: [{ topic_queue_id: 1, status: 'canceled' }],
        jobs: [{ id: 7, topic_queue_id: '2', status: 'pending' }],
    })
    const result = await lib.listTopicsForDeletion(db, 'ko', 1, 500)
    assert.match(result.topics.find(row => row.id === '1').delete_block_reason, /프로젝트/)
    assert.match(result.topics.find(row => row.id === '2').delete_block_reason, /생성 작업/)
})

test('bulk deletion deletes only selected unclaimed topics in the chosen country and preserves work history', async () => {
    const db = database([
        topic(1, { assigned_employee_email: 'reserved@example.com' }), topic(2, { status: 'excluded' }),
        topic(3, { category_id: 3 }), topic(4, { status: 'assigned' }),
        topic(5), topic(6, { status: 'excluded', assigned_at: '2026-01-01' }),
        topic(7), topic(8), topic(9),
    ], {
        projects: [{ topic_queue_id: 5, status: 'canceled' }],
        jobs: [{ id: 1, topic_id: '7', status: 'rendering' }, { id: 2, topic_queue_id: '8', status: 'completed' }],
    })
    const result = await lib.deleteSelectedTopics(db, ['1', '2', '3', '4', '5', '6', '7', '8', '404'], 'ko')
    assert.deepEqual(result.deletedIds, ['1', '2', '8'])
    assert.equal(result.deletedCount, 3)
    assert.deepEqual(result.skipped.map(row => row.id), ['3', '4', '5', '6', '7', '404'])
    assert.deepEqual(db.tables.topics_queue.map(row => row.id), [3, 4, 5, 6, 7, 9])
    assert.equal(db.tables.std_projects.length, 1)
    assert.equal(db.tables.remote_hermes_queue.length, 2)
})

test('a simultaneous claim is skipped and never reported as deleted', async () => {
    const db = database([topic(1), topic(2)], {
        beforeDelete(tables) { tables.topics_queue[0].status = 'assigned'; tables.topics_queue[0].assigned_at = '2026-01-01' },
    })
    const result = await lib.deleteSelectedTopics(db, ['1', '2'], 'ko')
    assert.deepEqual(result.deletedIds, ['2'])
    assert.equal(result.skipped[0].id, '1')
    assert.equal(db.tables.topics_queue[0].status, 'assigned')
})

test('protection lookup failures fail closed before any deletion', async () => {
    for (const table of ['categories', 'topics_queue', 'std_projects', 'remote_hermes_queue', 'script_worker_jobs']) {
        const db = database([topic(1)], { errorTable: table })
        await assert.rejects(() => lib.deleteSelectedTopics(db, ['1'], 'ko'))
        assert.equal(db.calls.filter(call => call.deletion).length, 0)
    }
})

test('linked projects beyond the API row limit remain protected', async () => {
    const projects = Array.from({ length: 1000 }, (_, index) => ({ id: index + 1, topic_queue_id: 1 }))
    projects.push({ id: 1001, topic_queue_id: 2 })
    const db = database([topic(1), topic(2)], { projects })
    const result = await lib.deleteSelectedTopics(db, ['1', '2'], 'ko')
    assert.equal(result.deletedCount, 0)
    assert.deepEqual(result.skipped.map(row => row.id), ['1', '2'])
    assert.equal(db.calls.filter(call => call.table === 'std_projects').length, 2)
})

test('local Codex repairs and approval-pending work preserve their source topic', async () => {
    const scriptJobs = [
        { id: 'a', status: 'running', source_id: '1', 'request_data->>source_id': '1', 'request_data->>kind': 'topic' },
        { id: 'b', status: 'awaiting_approval', source_id: '2', 'request_data->>source_id': '2', 'request_data->>kind': 'topic' },
        { id: 'c', status: 'approved_pending_repair', source_id: '3', 'request_data->>source_id': '3', 'request_data->>kind': 'topic' },
        { id: 'd', status: 'failed', source_id: '4', 'request_data->>source_id': '4', 'request_data->>kind': 'topic' },
    ]
    const db = database([topic(1), topic(2), topic(3), topic(4)], { scriptJobs })
    const result = await lib.deleteSelectedTopics(db, ['1', '2', '3', '4'], 'ko')
    assert.deepEqual(result.deletedIds, ['4'])
    assert.deepEqual(result.skipped.map(row => row.id), ['1', '2', '3'])
    assert.equal(db.tables.script_worker_jobs.length, 4)
})

test('database deletion failure reports zero deletions and explicit skipped IDs', async () => {
    const db = database([topic(1), topic(2)], { deleteError: true })
    const result = await lib.deleteSelectedTopics(db, ['1', '2'], 'ko')
    assert.equal(result.deletedCount, 0)
    assert.deepEqual(result.skipped.map(row => row.id), ['1', '2'])
    assert.equal(db.tables.topics_queue.length, 2)
})

test('large selections preserve exact deletion counts over multiple batches', async () => {
    const db = database(Array.from({ length: 205 }, (_, index) => topic(index + 1)))
    const ids = Array.from({ length: 205 }, (_, index) => String(index + 1))
    const result = await lib.deleteSelectedTopics(db, ids, 'ko')
    assert.equal(result.deletedCount, 205)
    assert.equal(result.skipped.length, 0)
    assert.equal(db.calls.filter(call => call.deletion).length, 3)
})

function route(authorized, db) {
    const response = (body, options = {}) => ({ body, status: options.status || 200, headers: options.headers })
    return loadTs('app/api/admin/topics-queue/bulk-delete/route.ts', {
        '@supabase/supabase-js': { createClient: () => db },
        'next/server': { NextResponse: { json: response } },
        '../../_auth': { requireSuperAdmin: async () => authorized ? { user: {} } : response({ error: 'Forbidden' }, { status: 403 }), isAuthResponse: value => Boolean(value.body) },
        '@/lib/adminTopicDeletion': lib,
    })
}

test('GET and DELETE reject non-super-admin callers without database reads', async () => {
    const db = database([topic(1)])
    const api = route(false, db)
    assert.equal((await api.GET(new Request('https://test/bulk-delete'))).status, 403)
    assert.equal((await api.DELETE(new Request('https://test/bulk-delete', { method: 'DELETE', body: '{"ids":[1],"language":"ko"}' }))).status, 403)
    assert.equal(db.calls.length, 0)
})

test('route validates malformed JSON, missing scope, and paging before touching database', async () => {
    const db = database([topic(1)])
    const api = route(true, db)
    for (const body of ['not-json', '{}', '{"ids":[1]}', '{"ids":[1],"language":"all"}']) {
        assert.equal((await api.DELETE(new Request('https://test/bulk-delete', { method: 'DELETE', body }))).status, 400)
    }
    for (const query of ['page=0', 'page=1.5', 'perPage=501', 'language=fr']) {
        assert.equal((await api.GET(new Request(`https://test/bulk-delete?${query}`))).status, 400)
    }
    assert.equal(db.calls.length, 0)
})
