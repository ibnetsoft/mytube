const fs = require('fs'), path = require('path'), { createRequire } = require('module')
const runtime = require('../scripts/std_web_runtime.cjs'), req = createRequire(path.join(runtime.web, 'package.json'))
const ts = req('typescript'), db = runtime.load('supabaseAdmin').supabaseAdmin
const release = fs.readFileSync('_dev/artifacts/project_completion_release_root.txt', 'utf8').trim()
const phase = process.argv[2] || 'before'
async function run() {
    const owner = await db.from('std_projects').select('employee_email').eq('topic_queue_id', 3376).limit(1).single()
    if (owner.error) throw owner.error
    const actual = await db.from('std_projects').select('id,title,topic_queue_id,category_id,created_at,updated_at,submitted_at,version:progress_payload->latest_render_version,thumb:project_payload->>thumbnail_url,progress_thumb:progress_payload->>thumbnail_url').eq('employee_email', owner.data.employee_email).order('updated_at', { ascending: false })
    if (actual.error) throw actual.error
    const ex = {}, source = fs.readFileSync(path.join(release, 'auth-web/app/api/std/projects/route.ts'), 'utf8')
    new Function('exports', 'require', ts.transpileModule(source, { compilerOptions: { module: 1, target: 9 } }).outputText)(ex, name => {
        if (name === '@/lib/stdWeb') return { requireStdUser: async () => ({ ok: true, requester: { email: owner.data.employee_email } }) }
        if (name.startsWith('@/lib/')) return runtime.load(name.slice('@/lib/'.length))
        return req(name)
    })
    const response = await ex.GET(new Request('https://audit.local/api/std/projects'))
    const payload = await response.json()
    if (!response.ok || !payload.projects) throw Error(JSON.stringify(payload))
    fs.writeFileSync(`_dev/artifacts/project_list_api_${phase}.json`, JSON.stringify(payload.projects.map(p => ({
        id: p.id, title: p.title, language: p.language, category_id: p.category_id, category_name: p.category_name,
        topic_queue_id: p.topic_queue_id, created_at: p.created_at, updated_at: p.updated_at,
        submitted_at: p.submitted_at, thumbnail_url: p.thumbnail_url, latest_render_version: p.latest_render_version,
        step_status: p.step_status, shared_submission: p.shared_submission, title_localization: p.title_localization,
    })), null, 2))
    const results = actual.data.map(saved => {
        const row = payload.projects.find(p => p.id === saved.id)
        if (!row) return { topic: saved.topic_queue_id, id: saved.id, errors: ['missing row'] }
        const displayedModified = phase === 'before' ? row.submitted_at || row.shared_submission?.submitted_at : row.updated_at
        const displayedVersion = phase === 'before' ? Math.max(Number(row.progress_payload?.latest_render_version) || 0, row.submitted_at || row.shared_submission ? 1 : 0) : row.latest_render_version || 0
        const displayedThumbnail = phase === 'before' ? row.progress_payload?.thumbnail_url || row.project_payload?.thumbnail_url || '' : row.thumbnail_url
        return { topic: saved.topic_queue_id, id: saved.id, title: saved.title, category: row.category_name,
            expected_version: Number(saved.version) || 0, displayed_version: displayedVersion,
            saved_updated_at: saved.updated_at, displayed_updated_at: displayedModified || null,
            has_saved_thumbnail: Boolean(saved.progress_thumb || saved.thumb), has_displayed_thumbnail: Boolean(displayedThumbnail),
            steps: row.step_status, errors: [
                row.title !== saved.title ? 'title' : '',
                row.category_id !== saved.category_id ? 'category' : '',
                row.topic_queue_id !== saved.topic_queue_id ? 'topic number' : '',
                row.created_at !== saved.created_at ? 'creation date' : '',
                displayedModified !== saved.updated_at ? 'modified date' : '',
                displayedVersion !== (Number(saved.version) || 0) ? 'render version' : '',
                Boolean(saved.progress_thumb || saved.thumb) && !displayedThumbnail ? 'thumbnail missing' : '',
            ].filter(Boolean) }
    })
    fs.writeFileSync(`_dev/artifacts/project_list_audit_${phase}.json`, JSON.stringify({ phase, rows: results.length, results }, null, 2))
    console.log(JSON.stringify({ phase, rows: results.length, errors: results.filter(r => r.errors.length).map(r => ({ topic: r.topic, id: r.id, errors: r.errors })), versions: results.filter(r => r.expected_version).map(r => ({ topic: r.topic, expected: r.expected_version, displayed: r.displayed_version })) }))
}
run().catch(error => { console.error(error.message); process.exitCode = 1 })
