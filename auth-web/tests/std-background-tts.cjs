const assert = require('node:assert/strict')
const fs = require('fs'), ts = require('typescript')
function load(file, deps) {
    const exports = {}
    new Function('require','exports',ts.transpile(fs.readFileSync(file,'utf8'),{module:1,target:7}))(
        id => deps[id] || require(id), exports)
    return exports
}
let job, project, calls, changes, failure
const db = {
    rpc: async () => ({ data: job ? [structuredClone(job)] : [], error: null }),
    from: () => ({ update: values => ({ eq() { return this }, select() { return this }, single: async () => {
        changes.push(values); Object.assign(job, values); return { data: { id: job.id }, error: null }
    } }) }),
}
const api = load('auth-web/lib/stdTtsJobs.ts', {
    './supabaseAdmin': { supabaseAdmin: db },
    './stdNarrationBatch': { BACKGROUND_NARRATION_BATCH_SIZE: 16 },
    './stdTtsGenerate': {
        loadStdProject: async () => ({ data: project }),
        runTts: async (body, auth, snapshot, finalize, id) => {
            calls.push(body); assert.equal(id, 'job'); assert.equal(finalize, true)
            if (failure) throw Error('temporary provider error')
            return { ok: true, json: async () => body.mode === 'prepare_narration_segments'
                ? { success: true, prepared: body.voice_segments.length, segment_reuse: { reused: body.voice_segments.length, generated: 0 } }
                : { success: true, asset: { id: 'final-audio' } } }
        },
    },
})
function setup() {
    project = { employee_email: 'owner', project_payload: { script: 'script', subtitles: [{ text: 'hello' }] } }
    job = { id: 'job', project_id: 'project', owner_email: 'owner', user_id: 'user', source_hash: api.ttsSourceHash(project),
        script: 'script', request: { voice_segments: Array.from({ length: 33 }, (_, i) => ({ text: String(i), voice_id: 'voice' })) },
        ready: 0, total: 33, reused: 0, generated: 0, attempts: 0, lease_token: 'lease' }
    calls = []; changes = []; failure = false
}
;(async () => {
    setup(); await api.processTtsJobs()
    assert.deepEqual(calls.map(c => c.voice_segments.length), [16,16,1,33])
    assert.equal(job.status, 'completed'); assert.equal(job.ready, 33)
    assert.equal(job.reused, 33); assert.equal(job.generated, 0)
    assert.deepEqual(job.request, {}); assert.equal(job.lease_token, null)
    setup(); job.ready = 16; await api.processTtsJobs()
    assert.deepEqual(calls[0].voice_segments[0].text, '16')
    setup(); failure = true; await api.processTtsJobs()
    assert.equal(job.status, 'queued'); assert.equal(job.ready, 0); assert.equal(job.attempts, 1)
    job.attempts = 2; await api.processTtsJobs(); assert.equal(job.status, 'failed')
    setup(); project.project_payload.subtitles[0].text = 'edited'; await api.processTtsJobs()
    assert.equal(calls.length, 0, 'Edited source must not generate or attach stale audio')
    setup(); project.progress_payload = { background_tts_job_id: 'job', subtitle_tts_completed: true, tts_asset_id: 'saved' }
    await api.processTtsJobs(); assert.equal(calls.length, 0); assert.equal(job.result.asset_id, 'saved')
    assert.equal(api.publicTtsJob(job).request, undefined)
    job = null; assert.deepEqual(await api.processTtsJobs(), { idle: true })
    console.log('PASS: durable checkpoints, resume, bounded slices, retries, source edits, post-save crash recovery and safe status projection')
})().catch(error => { console.error(error); process.exitCode = 1 })
