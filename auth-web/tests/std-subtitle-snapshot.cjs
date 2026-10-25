const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
const modules = new Map();
function load(filename) {
    const full = path.resolve(filename);
    if (modules.has(full)) return modules.get(full);
    const exports = {};
    modules.set(full, exports);
    new Function('exports', 'require', ts.transpile(fs.readFileSync(full, 'utf8'), { module: 1, target: 7 }))(exports,
        name => load(path.resolve(path.dirname(full), `${name}.ts`)));
    return exports;
}
const { restoreSavedSubtitleSnapshot } = load('auth-web/lib/stdSubtitleSnapshot.ts');
const { subtitlesMatchSceneManifest } = load('auth-web/lib/stdSubtitleSceneIntegrity.ts');
const { subtitleSpeaker } = load('auth-web/lib/stdSpeakerAssignment.ts');
const { alignedNarrationSubtitles } = load('auth-web/lib/stdPreviewAudio.ts');
const scenes = [{ scene_number: 1 }, { scene_number: 2 }, { scene_number: 3 }];
let generated = 0;
const initial = () => { generated++; return [{ text: 'Generated draft', scene_number: 1 }]; };

const saved = [
    { id: 'custom-a', scene_number: 1, text: 'ユーザーが修正した台詞', start_num: 2.35, end_num: 7.9, start_time: '2.35', end_time: '7.90',
        voice_id: 'eleven-male', voice_name: 'Male actor', editor_speaker: { name: '仙太郎', gender: 'male', text: 'ユーザーが修正した台詞' },
        dialogue_override: true, volume: 74, audio_url: 'saved-dialogue.mp3' },
    { id: 'custom-b', scene_number: 3, text: '「はい」と答えた。', start_num: 10.25, end_num: 18.875, start_time: '10.25', end_time: '18.875',
        voice_id: 'narrator', voice_name: 'Narrator', dialogue_override: false },
    { id: 'split-a', scene_number: 3, text: '分けた文', start_num: 19, end_num: 20.2, voice_id: 'female',
        editor_speaker: { name: 'お鈴', gender: 'female', text: '分けた文' } },
    { id: 'split-b', scene_number: 3, text: 'です', start_num: 20.2, end_num: 21.7, voice_id: 'female',
        editor_speaker: { name: 'お鈴', gender: 'female', text: 'です' } },
];
const before = structuredClone(saved);
assert.equal(subtitlesMatchSceneManifest(saved, scenes), false, 'This edited snapshot intentionally has no scene 2');
const reopened = restoreSavedSubtitleSnapshot(saved, initial);
assert.equal(generated, 0, 'Scene gaps or changed text must never regenerate saved edits');
assert.deepEqual(reopened, saved, 'Every saved text, split, custom time, actor and editor field survives reopening');
assert.deepEqual(saved, before, 'Restoration never mutates database records');
assert.deepEqual(restoreSavedSubtitleSnapshot(reopened, initial), reopened, 'Repeated reopening is stable');
assert.equal(reopened[1].voice_id, 'narrator', 'A merged dialogue/narration row retains the chosen voice');
assert.equal(reopened.length, 4, 'An intentional short-word split is preserved');

const punctuation = [
    { id: 'speech', scene_number: 4, text: 'ありがとう', start_num: 31.125, end_num: 32.5, start_time: '31.125', end_time: '32.5',
        voice_id: 'female', voice_name: 'Selected actress', audio_url: 'recorded.mp3', audio_duration: 1.375,
        editor_speaker: { name: 'お鈴', gender: 'female', text: 'ありがとう' } },
    { id: 'punctuation', scene_number: 4, text: '。', start_num: 32.5, end_num: 32.9, voice_id: 'narrator' },
];
const repaired = restoreSavedSubtitleSnapshot(punctuation, initial);
assert.equal(repaired.length, 1);
assert.equal(repaired[0].text, 'ありがとう。');
assert.equal(repaired[0].start_num, 31.125);
assert.equal(repaired[0].end_num, 32.9, 'Only the punctuation interval extends the preceding subtitle');
assert.equal(repaired[0].voice_id, 'female');
assert.equal(repaired[0].audio_url, 'recorded.mp3');
assert.equal(repaired[0].audio_duration, 1.375);
assert.deepEqual(subtitleSpeaker(repaired[0], undefined, []), { name: 'お鈴', gender: 'female', label: 'お鈴' },
    'Punctuation repair keeps the manual speaker confirmation current');
assert.equal(punctuation[0].editor_speaker.text, 'ありがとう');
const aligned = alignedNarrationSubtitles([{ text: '冒頭', voice_id: 'narrator' }, ...repaired], [
    { text: '冒頭', start: 0, end: 31.125, voice_id: 'narrator' },
    { text: 'ありがとう', start: 31.125, end: 32.5, voice_id: 'female' },
    { text: '。', start: 32.5, end: 32.9, voice_id: 'narrator' },
]);
assert(aligned, 'Recorded narration still aligns after attaching punctuation');
assert.equal(aligned[1].start_num, 31.125);
assert.equal(aligned[1].end_num, 32.9);

const stale = [{ ...punctuation[0], editor_speaker: { name: 'Old name', gender: 'male', text: 'Different old text' } }, punctuation[1]];
assert.equal(subtitleSpeaker(restoreSavedSubtitleSnapshot(stale, initial)[0], undefined, []), null,
    'Normalization never revives metadata already stale before the repair');

for (const absent of [undefined, null, [], {}]) assert.deepEqual(restoreSavedSubtitleSnapshot(absent, initial), [{ text: 'Generated draft', scene_number: 1 }]);
assert.equal(generated, 4, 'Generation is restricted to projects without a saved snapshot');
console.log('PASS: authoritative saved edits survive scene gaps, changed text, custom timing, split/merged rows and voice metadata; punctuation keeps speaker and recorded narration; empty projects still generate');

const quoteTail = [
 {id:'sub-71-4',scene_number:71,text:'困った時は人に頼ります」',voice_id:'actor',dialogue_kind:'dialogue',dialogue_speaker:'お紬',start_num:10,end_num:12},
 {id:'sub-71-4-quote-2',scene_number:71,text:'言',voice_id:'narrator',dialogue_kind:'narration',start_num:12,end_num:12.7,start:12,end:12.7},
 {id:'sub-71-5',scene_number:71,text:'い終えると涙が落ちた。',voice_id:'narrator',dialogue_kind:'narration',start_num:12.7,end_num:15,start:12.7,end:15},
];
const forward=restoreSavedSubtitleSnapshot(quoteTail,initial);
assert.equal(forward.length,2);
assert.equal(forward[0].text,quoteTail[0].text,'Do not append narration to dialogue');
assert.equal(forward[1].text,'言い終えると涙が落ちた。');
assert.equal(forward[1].voice_id,'narrator');assert.equal(forward[1].start_num,12);assert.equal(forward[1].end_num,15);assert.equal(forward[1].end,15);
assert.equal(quoteTail[1].text,'言','Never mutate saved input');
assert.deepEqual(restoreSavedSubtitleSnapshot(forward,initial),forward);
for(const modify of [r=>r[1].id='intentional-single',r=>r[2].voice_id='different',r=>r[2].scene_number=72,r=>r[2].start_num=14,r=>r[1].dialogue_kind='dialogue']){
 const rows=structuredClone(quoteTail);modify(rows);assert.equal(restoreSavedSubtitleSnapshot(rows,initial).length,3);
}
const voiceTimeline=quoteTail.map(r=>({text:r.text,voice_id:r.voice_id,start:r.start_num-10,end:r.end_num-10}));
assert(alignedNarrationSubtitles(forward,voiceTimeline),'Final recorded voice stays reusable when adjacent narration rows merge');
console.log('PASS: quote-split kanji attaches to following narration with exact recorded bounds; intentional splits, other speakers and scenes survive');
