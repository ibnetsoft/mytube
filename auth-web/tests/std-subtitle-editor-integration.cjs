const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');

const source = fs.readFileSync('auth-web/app/std/page.tsx', 'utf8');
const ast = ts.createSourceFile('page.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function find(root, predicate) {
    if (predicate(root)) return root;
    let match;
    ts.forEachChild(root, child => { if (!match) match = find(child, predicate); });
    return match;
}
function variable(root, name) {
    const match = find(root, node => ts.isVariableDeclaration(node) && node.name.getText(ast) === name);
    assert(match?.initializer, `Missing ${name}`);
    return match.initializer;
}
function evaluate(expression, dependencies) {
    const code = ts.transpile(`const value = (${expression.getText(ast)}); return value;`, { module: 1, target: 7, jsx: 4 });
    return new Function('exports', ...Object.keys(dependencies), code)({}, ...Object.values(dependencies));
}
const cache = new Map();
function load(filename) {
    const full = path.resolve(filename);
    if (cache.has(full)) return cache.get(full);
    const exports = {};
    cache.set(full, exports);
    new Function('exports', 'require', ts.transpile(fs.readFileSync(full, 'utf8'), { module: 1, target: 7 }))(exports,
        name => load(path.resolve(path.dirname(full), `${name}.ts`)));
    return exports;
}
const { restoreSavedSubtitleSnapshot } = load('auth-web/lib/stdSubtitleSnapshot.ts');
const saved = [
    { id: 'manual-1', text: '「ユーザーの修正」と言った。', scene_number: 1, start_num: 2.1, end_num: 7.55, start_time: '2.1', end_time: '7.55',
        voice_id: 'manual-actor', editor_speaker: { name: '仙太郎', gender: 'male', text: '「ユーザーの修正」と言った。' }, dialogue_override: true },
    { id: 'manual-2', text: '短く分割', scene_number: 3, start_num: 21, end_num: 24, start_time: '21', end_time: '24', voice_id: 'narrator' },
    { id: 'manual-3', text: 'です', scene_number: 3, start_num: 24, end_num: 25.1, start_time: '24', end_time: '25.1', voice_id: 'narrator' },
];
const scenes = [{ scene_number: 1 }, { scene_number: 2 }, { scene_number: 3 }];
const selectedProject = { project: { id: 'edited-project', project_payload: { script: 'Original unrelated draft', subtitles: saved } }, scenes };
let generations = 0;
const generate = () => { generations++; throw new Error('Saved edits must not regenerate'); };
const common = { selectedProject, restoreSavedSubtitleSnapshot, subMaxChars: '20', generateSynchronizedSubtitles: generate,
    generateAnnotatedSubtitles: generate, cleanScriptContextText: value => value || '', customScriptText: '' };

// Execute the expressions from the actual page, so all three reload/sync paths
// must choose the saved editor rows even when script and scene coverage differ.
const open = variable(ast, 'openProject');
const reopened = evaluate(variable(open, 'projectSubtitles'), { ...common, storedServerSubtitles: saved,
    fullScript: 'Original unrelated draft', normalizedScenes: scenes, payload: selectedProject });
assert.deepEqual(reopened, saved);
const hydration = find(ast, node => ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect'
    && node.arguments[0]?.getText(ast).includes('const savedSubtitles ='));
assert(hydration, 'Project hydration effect exists');
const hydrated = evaluate(variable(hydration, 'subs'), { ...common, savedSubtitles: saved, scenes, currentScript: 'Original unrelated draft' });
assert.deepEqual(hydrated, saved);
const sync = variable(ast, 'handleSyncSubtitleSceneVisuals');
const synced = evaluate(variable(sync, 'baseSubtitles'), { ...common, scenes, localSubtitles: saved });
assert.deepEqual(synced, saved);
assert.equal(generations, 0);

const matchSubtitlesToSceneVisuals = evaluate(variable(ast, 'matchSubtitlesToSceneVisuals'), {
    ...common, subtitleSceneVisual: subtitle => ({ scene_number: subtitle.scene_number, image_url: 'fresh.jpg', video_url: null }),
});
const visualRows = matchSubtitlesToSceneVisuals(saved, scenes);
assert.deepEqual(visualRows.map(({ image_url, video_url, ...row }) => row), saved,
    'Media synchronization cannot re-split saved text or clear the selected voice');

const subtitleHasValidTiming = evaluate(variable(ast, 'subtitleHasValidTiming'), {});
const ensureSubtitlesHaveTiming = evaluate(variable(ast, 'ensureSubtitlesHaveTiming'), { selectedProject, subtitleHasValidTiming,
    calculateLongformSceneTimings: rows => rows.map((row, index) => ({ start_time: index * 5, end_time: (index + 1) * 5, duration: 5 })),
});
const partlyUntimed = [saved[0], { id: 'old-untimed', scene_number: 1, text: 'Older row without timing' }, ...saved.slice(1)];
const repairedHydration = evaluate(variable(hydration, 'normalizedSubtitles'), { ...common, subs: partlyUntimed, scenes,
    matchSubtitlesToSceneVisuals, ensureSubtitlesHaveTiming });
assert.equal(repairedHydration[0].start_num, 2.1);
assert.equal(repairedHydration[0].end_num, 7.55, 'An untimed sibling never redistributes a saved custom interval');
assert(subtitleHasValidTiming(repairedHydration[1]), 'An older untimed row still receives usable timing');

const buildPersistentProjectState = evaluate(variable(ast, 'buildPersistentProjectState'), {
    ...common, sanitizeAssetUrl: value => value || null, directStorageUrl: () => null, projectAssetFileUrl: () => null,
});
assert.deepEqual(buildPersistentProjectState(selectedProject).project.project_payload.subtitles, saved,
    'The local cache preserves merged dialogue and intentional short-word splits');

// Check the actual button behavior. Saving edits must remain available while
// Save+TTS is unavailable, and it must invoke persistence rather than an alert.
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
const saveButton = find(ast, node => ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === 'button'
    && node.openingElement.getText(ast).includes('TTS를 생성하지 않고 수정 내용을 저장합니다'));
assert(saveButton, 'A standalone subtitle save control exists');
let saves = 0;
for (const state of ['idle', 'dirty', 'error', 'saved']) {
    const button = evaluate(saveButton, { require: () => jsx, Save: () => null, RefreshCw: () => null, currentLocale: 'ko', subtitleSaveState: state,
        localSubtitles: saved, canFinalizeSubtitlesAndTts: false, handleSaveSubtitles: async () => { saves++; } });
    assert.equal(button.type, 'button');
    assert.equal(button.props.type, 'button');
    assert.equal(button.props.disabled, false, `${state}: text edits can save independently of TTS eligibility`);
    button.props.onClick();
}
assert.equal(saves, 4);
const selectionSave = find(ast, node => ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === 'button'
    && node.openingElement.getText(ast).includes('handleSaveSubtitles') && node.getText(ast).includes("t('btn_save')"));
assert(selectionSave, 'Selected-range Save invokes the real persistence handler');

const timingButtons = [];
(function visit(node) {
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === 'button'
        && node.openingElement.getText(ast).includes('adjustSubtitleTiming')) timingButtons.push(node);
    ts.forEachChild(node, visit);
})(ast);
assert.equal(timingButtons.length, 6, 'All range/start/end +/- controls persist timing edits');
const adjustments = [];
for (const node of timingButtons) {
    const button = evaluate(node, { require: () => jsx, selectedSubIndex: 2, adjustSubtitleTiming: (...args) => adjustments.push(args) });
    assert.equal(button.props.type, 'button');
    button.props.onClick();
}
assert.deepEqual(adjustments, [[2, 'both', -0.1], [2, 'both', 0.1], [2, 'start', -0.1], [2, 'start', 0.1], [2, 'end', -0.1], [2, 'end', 0.1]]);

for (const [start, end, delta, expectedStart, expectedEnd] of [[3, 3.1, 0.1, 3.1, 3.2], [3, 3.15, 0.1, 3.1, 3.25], [0.05, 0.2, -0.1, 0, 0.15]]) {
    let persisted;
    const adjust = evaluate(variable(ast, 'adjustSubtitleTiming'), {
        speechSubtitlesRef: { current: [{ text: 'Short subtitle', start_num: start, end_num: end }] },
        persistVrewVoiceSubtitles: rows => { persisted = rows; },
    });
    adjust(0, 'both', delta);
    assert.equal(persisted[0].start_num, expectedStart);
    assert.equal(persisted[0].end_num, expectedEnd, 'Shifting a short subtitle preserves its duration');
}

(async () => {
    const writes = [];
    const stopBeforeAudio = new Error('Stop before creating an audio element');
    const play = evaluate(variable(ast, 'playVrewSegmentsFrom'), {
        localSubtitles: saved, selectedProject: { ...selectedProject, assets: [{ id: 'saved-audio', metadata: { subtitle_timeline: [] } }] },
        selectedVoice: 'narrator', speechContextRef: { current: { resume: async () => {} } },
        vrewPlaybackCancelRef: { current: 0 }, vrewFinalNarrationAudioRef: { current: { assetId: 'saved-audio' } },
        setIsPlayingPreview() {}, setIsNarrationPlaying() {}, setPreviewAudioError() {}, setHighlightSaveTts() {}, setMessage() {},
        getSavedNarrationAudioUrl: async () => 'saved-audio.mp3',
        alignedNarrationSubtitles: rows => rows.map((row, index) => ({ ...row, start_num: index, end_num: index + 1 })),
        setLocalSubtitles: rows => writes.push(rows),
        prepareSpeechPlayback: async () => { throw stopBeforeAudio; },
    });
    await assert.rejects(play(0), error => error === stopBeforeAudio);
    assert.deepEqual(writes, [], 'Previewing saved narration never replaces custom editor timing with an old TTS timeline');

    const speech = { ...saved[0], text: 'first second', editor_speaker: { ...saved[0].editor_speaker, text: 'first second' } };
    let textRows;
    const textEditor = find(ast, node => ts.isJsxSelfClosingElement(node) && node.tagName.getText(ast) === 'textarea'
        && node.getText(ast).includes('scheduleSubtitleTextSave'));
    assert(textEditor, 'Subtitle text editor schedules a real save');
    const textarea = evaluate(textEditor, {
        require: () => jsx, currentSub: speech, selectedSubIndex: 0, subtitleTextEditorRef: { current: null },
        speechSubtitlesRef: { current: [speech] }, isSubtitleDialogue: () => true,
        isVrewSubtitleMode: true, isPlayingPreview: false, markVrewSegmentStale() {},
        scheduleSubtitleTextSave: rows => { textRows = rows; },
    });
    textarea.props.onChange({ target: { value: 'edited first second' } });
    assert.equal(textRows[0].editor_speaker.name, speech.editor_speaker.name);
    assert.equal(textRows[0].editor_speaker.text, textRows[0].text);
    assert.equal(textRows[0].voice_id, speech.voice_id);

    function actions(rows, indexes, succeeds) {
        const messages = [];
        let persisted;
        const dependencies = { localSubtitles: rows, selectedSubtitleBlockIndexes: indexes, currentNav: 'subtitle_vrew',
            isPlayingPreview: false, isSubtitleDialogue: () => true, aiDialogueParts: new Map(),
            subtitleSpeakers: rows.map(row => ({ name: row.editor_speaker?.name })),
            subtitleTextSelectionRef: { current: { subtitleIndex: 0, cursor: 5 } },
            subtitleBlockSelectionAnchorRef: { current: null }, subtitleTranslationControllerRef: { current: null },
            subtitleTranslationRequestRef: { current: '' }, subtitleReviewLocale: '',
            setSelectedSubIndex() {}, setSelectedSubtitleBlockIndexes() {}, setTranslatingSubtitleLanguage() {},
            markVrewSegmentStale() {}, setMessage: message => messages.push(message),
            persistVrewVoiceSubtitles: async value => { persisted = value; return succeeds; },
            selectedVoice: 'narrator', voiceNameById: new Map([['new-actor', 'New actor']]),
        };
        return { messages, dependencies, get persisted() { return persisted; } };
    }
    for (const succeeds of [true, false]) {
        const split = actions([speech], [0], succeeds);
        await evaluate(variable(ast, 'splitSelectedSubtitleBlock'), split.dependencies)();
        assert.equal(split.persisted.length, 2);
        assert.equal(split.persisted[0].start_num, speech.start_num);
        assert.equal(split.persisted[1].end_num, speech.end_num);
        assert.equal(split.persisted[0].end_num, split.persisted[1].start_num);
        for (const row of split.persisted) {
            assert.equal(row.editor_speaker.name, speech.editor_speaker.name);
            assert.equal(row.editor_speaker.text, row.text);
            assert.equal(row.voice_id, speech.voice_id);
        }
        assert.equal(split.messages.length, succeeds ? 1 : 0, 'A failed split save must not display success');
        const merged = actions(split.persisted, [0, 1], succeeds);
        await evaluate(variable(ast, 'mergeSelectedSubtitleBlocks'), merged.dependencies)();
        assert.equal(merged.persisted.length, 1);
        assert.equal(merged.persisted[0].text, speech.text);
        assert.equal(merged.persisted[0].editor_speaker.text, speech.text);
        assert.equal(merged.persisted[0].voice_id, speech.voice_id);
        assert.equal(merged.messages.length, succeeds ? 1 : 0, 'A failed merge save must not display success');
        const bulk = actions(split.persisted, [0, 1], succeeds);
        await evaluate(variable(ast, 'setSelectedSubtitleBlocksVoice'), bulk.dependencies)('new-actor');
        assert(bulk.persisted.every(row => row.voice_id === 'new-actor'));
        assert.equal(bulk.messages.length, succeeds ? 1 : 0, 'A failed bulk voice save must not display success');
    }
    const differentSpeakers = actions([speech, { ...speech, id: 'other-speaker',
        editor_speaker: { ...speech.editor_speaker, name: '花代', gender: 'female' } }], [0, 1], true);
    await evaluate(variable(ast, 'mergeSelectedSubtitleBlocks'), differentSpeakers.dependencies)();
    assert.equal(differentSpeakers.persisted, undefined, 'Different manually confirmed speakers cannot merge merely because AI annotations are absent');
    assert.equal(differentSpeakers.messages.length, 1);
    console.log('PASS: actual page reload/sync/cache preserve edited rows/timing; native save/time controls persist; preview keeps editor times; text/split/merge preserve speaker; failed edits never announce success');
})().catch(error => { console.error(error); process.exitCode = 1; });
