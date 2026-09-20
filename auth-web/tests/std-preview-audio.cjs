const fs = require('fs'), ts = require('typescript'), assert = require('node:assert/strict');
const api = {};
new Function('exports', ts.transpile(fs.readFileSync('auth-web/lib/stdPreviewAudio.ts', 'utf8'), { module: 1, target: 7 }))(api);
const media = new EventTarget();
let active = false, starts = 0;
const dispose = api.bindNarrationPlayback(media, () => { active = true; starts++; }, () => { active = false; });
// A resolved file request/metadata alone must never start effects or background music.
media.dispatchEvent(new Event('loadedmetadata'));
assert.equal(active, false);
assert.equal(starts, 0);
media.dispatchEvent(new Event('error'));
assert.equal(starts, 0);
media.dispatchEvent(new Event('playing'));
assert.equal(active, true);
for (const event of ['waiting', 'pause', 'ended', 'error']) {
    media.dispatchEvent(new Event(event));
    assert.equal(active, false);
    media.dispatchEvent(new Event('playing'));
    assert.equal(active, true);
}
dispose();
assert.equal(active, false);
const previous = starts;
media.dispatchEvent(new Event('playing'));
assert.equal(starts, previous);
assert.equal(api.narrationLoadError('{"detail":"drive_token_refresh_failed: invalid_grant"}', 404), '');
assert.match(api.narrationLoadError('upstream unavailable', 503), /503/);
const page = fs.readFileSync('auth-web/app/std/page.tsx', 'utf8');
assert.match(page, /playing=\{isVrewSubtitleMode \? isNarrationPlaying : isPlayingPreview\}/);
assert.match(page, /previewAudioError && <div role="alert"/);
console.log('PASS: narration loading/failure stays silent, playback resumes auxiliary layers, stop/dispose stops them, Drive recovery message visible');

(async()=>{let calls=0,repairs=0;await assert.rejects(()=>api.resolveStoredSegmentAudio(async()=>{calls++;return {cached:true,asset:{drive_file_id:'old',metadata:{}}}},async()=>{throw Object.assign(new Error('auth'),{code:'legacy_drive_auth_failed'})},()=>repairs++));assert.equal(calls,1);assert.equal(repairs,0);console.log('PASS: Drive auth failure never requests paid regeneration');})().catch(e=>{console.error(e);process.exitCode=1});
