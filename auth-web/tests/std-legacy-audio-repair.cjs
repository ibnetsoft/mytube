const fs = require('fs'), ts = require('typescript'), assert = require('node:assert/strict');
const api = {};
new Function('exports', ts.transpile(fs.readFileSync('auth-web/lib/stdPreviewAudio.ts', 'utf8'), { module: 1, target: 7 }))(api);
(async () => {
    const legacy = { cached: true, asset: { drive_file_id: 'old', metadata: {} } };
    const stored = { cached: true, asset: { metadata: { storage_path: 'saved.mp3' } } };
    const failure = Object.assign(new Error('expired'), { code: 'legacy_drive_auth_failed' });
    let persisted = false, repairs = 0, calls = [];
    const request = async repair => {
        calls.push(Boolean(repair));
        if (repair) persisted = true;
        return persisted ? stored : legacy;
    };
    const read = async payload => { if (payload === legacy) throw failure; return 'blob:saved'; };
    assert.equal(await api.resolveStoredSegmentAudio(request, read, () => repairs++), 'blob:saved');
    assert.deepEqual(calls, [false, true]);
    calls = [];
    await api.resolveStoredSegmentAudio(request, read, () => repairs++);
    assert.deepEqual(calls, [false]);
    assert.equal(repairs, 1, 'Later playback reuses the stored replacement');
    for (const [payload, error] of [[stored, failure], [legacy, new Error('network')], [{ cached: false }, failure]]) {
        let requests = 0;
        await assert.rejects(api.resolveStoredSegmentAudio(async () => { requests++; return payload; }, async () => { throw error; }, () => {}));
        assert.equal(requests, 1, 'Never regenerate for Storage/network/fresh-generation failures');
    }
    let attempts = 0;
    await assert.rejects(api.resolveStoredSegmentAudio(async () => { attempts++; return legacy; }, async () => { throw failure; }, () => {}));
    assert.equal(attempts, 2, 'Do not loop if repair also fails');
    console.log('PASS: legacy auth failure repairs once, persisted reuse, no retries for unrelated failures');
})().catch(error => { console.error(error); process.exit(1); });
