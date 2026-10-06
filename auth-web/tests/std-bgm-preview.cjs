const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const page = fs.readFileSync(require.resolve('../app/std/page.tsx'), 'utf8');
function compile(start, end, name, context) {
    const src = page.slice(page.indexOf(start), page.indexOf(end, page.indexOf(start)));
    return new Function(...Object.keys(context), ts.transpile(src + `\nreturn ${name}`, { target: ts.ScriptTarget.ES2020 }))(...Object.values(context));
}
const mix = {};
new Function('exports', ts.transpile(fs.readFileSync(require.resolve('../lib/stdAudioMix.ts'), 'utf8'), { module: ts.ModuleKind.CommonJS }))(mix);
const bgmRangeRef = { current: { start: 0, end: 100, valid: true, fadeIn: 0, fadeOut: 0 } };
const volumeUpdater = loop => compile('    const updatePreviewBgmVolume =', '    const playPreviewBgm =', 'updatePreviewBgmVolume', {
    ...mix, bgmRangeRef, bgmLoop: loop, bgmVolume: .08,
});
let played = false;
const bgm = { duration: 30, readyState: 1, currentTime: 0, volume: 1, play: () => { played = true; return Promise.resolve(); } };
const playBgm = compile('    const playPreviewBgm =', '    const stopVrewPlayback', 'playPreviewBgm', {
    bgmRangeRef, updatePreviewBgmVolume: volumeUpdater(true), previewBgmAudioRef: { current: bgm }, bgmLoop: true, bgmVolume: 0.08, backgroundVolume: v => v, HTMLMediaElement: { HAVE_METADATA: 1 }, setMessage: () => { },
});
playBgm(65);
assert.equal(played, true);
assert.equal(bgm.currentTime, 5);
assert.equal(bgm.volume, 0.08);
played = false;
bgm.pause = () => { };
const playOnce = compile('    const playPreviewBgm =', '    const stopVrewPlayback', 'playPreviewBgm', {
    bgmRangeRef, updatePreviewBgmVolume: volumeUpdater(false), previewBgmAudioRef: { current: bgm }, bgmLoop: false, bgmVolume: 0.08, backgroundVolume: v => v, HTMLMediaElement: { HAVE_METADATA: 1 }, setMessage: () => { },
});
playOnce(65);
assert.equal(played, false);
assert.equal(bgm.currentTime, 30);
playOnce(10);
assert.equal(played, true);
assert.equal(bgm.currentTime, 10);
bgmRangeRef.current.fadeOut = 4;
playOnce(28);
assert.equal(bgm.volume, .04, 'saved fade reaches half volume two seconds before a 30-second source ends');
bgm.readyState = 0;
bgm.duration = NaN;
let metadataCallback;
bgm.addEventListener = (event, callback) => { assert.equal(event, 'loadedmetadata'); metadataCallback = callback; };
playOnce(29);
bgm.duration = 30;
metadataCallback();
assert.equal(bgm.volume, .02, 'late metadata must update the fade before starting playback');
console.log('PASS: preview gain follows source duration for loops, one-shot playback and delayed metadata');
bgm.readyState = 1;
bgmRangeRef.current = mix.backgroundWindow({bgm_start_scene:100,bgm_start_subtitle:2,bgm_end_scene:101,bgm_fade_in:0,bgm_fade_out:0},[
    {scene_number:100,start_num:0,end_num:2},
    {scene_number:100,start_num:2,end_num:5},
    {scene_number:101,start_num:5,end_num:10},
],10);
played = false;
playOnce(1);
assert.equal(played,false,'do not start before the chosen subtitle');
playOnce(2);
assert.equal(bgm.currentTime,0);
playOnce(6);
assert.equal(bgm.currentTime,4,'next scene continues four seconds into the same track');
assert.equal(bgm.volume,.08);
console.log('PASS: BGM starts at selected subtitle and keeps its offset in later scenes');
