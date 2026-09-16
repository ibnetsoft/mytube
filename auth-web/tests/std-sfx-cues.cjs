const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const compile = source => ts.transpile(source, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 })
const api = {}
new Function('exports', compile(fs.readFileSync('auth-web/lib/stdSfxCues.ts', 'utf8')))(api)
const subtitle = { id: 'a', text: '문을 열고 들어왔다', start_num: 10, end_num: 16, scene_number: 3 }
const cue = { id: 'cue1', asset_id: 'sound', subtitle_id: 'a', subtitle_index: 0, word_boundary: 1, enabled: true, volume_db: -18 }
assert.equal(api.wordBoundaryTime(subtitle, 0), 10)
assert.equal(api.wordBoundaryTime(subtitle, 1), 12)
assert.equal(api.wordBoundaryTime(subtitle, 3), 16)
assert.equal(api.resolveSfxCues([cue], [subtitle])[0].start, 12)
const moved = api.resolveSfxCues([cue], [{ id: 'new' }, { ...subtitle, start_num: 20, end_num: 26 }])[0]
assert.equal(moved.subtitle_index, 1)
assert.equal(moved.start, 22)
assert.deepEqual(api.resolveSfxCues([cue], [{ id: 'unrelated', text: subtitle.text }]), [])
assert.deepEqual(api.resolveSfxCues([{ ...cue, enabled: false }], [subtitle]), [])
assert.equal(api.resolveSfxCues([{ start: 7 }], [subtitle])[0].start, 7)
const duplicate = { ...cue, id: 'cue2', word_boundary: 2 }
assert.deepEqual(api.resolveSfxCues([cue, duplicate], [subtitle]).map(c => c.start), [12, 14])
const queue = fs.readFileSync('auth-web/lib/stdRenderQueue.ts', 'utf8')
const section = queue.slice(queue.indexOf('    const savedSfxCues ='), queue.indexOf('    const renderSettings =', queue.indexOf('    const savedSfxCues =')))
const build = new Function('projectRenderSettings', 'project', 'subtitles', 'assetById', 'storageSourceForAsset', 'audioManifestPath', 'clampNumber', 'resolveSfxCues', compile('const manifestFiles=[];' + section + '\nreturn {manifestFiles,sfxCues}'))
const asset = { id: 'sound', file_name: 'door.mp3', metadata: { storage_bucket: 'content-assets', storage_path: 'std-projects/project/door.mp3' } }
const result = build({ sfx_cues: [cue, duplicate] }, { project_payload: { subtitles: [subtitle] } }, [subtitle], new Map([['sound', asset]]), a => a ? { bucket: a.metadata.storage_bucket, path: a.metadata.storage_path } : null, (a, p, i) => `audio/sfx-${i}.mp3`, (v, d) => Number.isFinite(Number(v)) ? Number(v) : d, api.resolveSfxCues)
assert.equal(result.manifestFiles.length, 2)
assert(result.manifestFiles.every(f => f.supabase_bucket === 'content-assets' && f.supabase_path === asset.metadata.storage_path))
assert.deepEqual(result.sfxCues.map(c => c.start), [12, 14])
assert(result.sfxCues.every(c => c.volume_db === -18))
console.log('PASS: word boundary timing, multiple inserts, reordered/deleted anchors, legacy cues, Storage-only render manifest')
