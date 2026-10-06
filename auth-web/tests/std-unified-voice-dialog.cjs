const fs = require('fs');
const path = require('path');
const ts = require('typescript');
const assert = require('node:assert/strict');
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
const modules = new Map();
function loadModule(filename, overrides = {}) {
    const resolved = path.resolve(filename);
    if (!Object.keys(overrides).length && modules.has(resolved)) return modules.get(resolved);
    const exports = {};
    const code = ts.transpile(fs.readFileSync(resolved, 'utf8'), { module: 1, target: 7, jsx: 4 });
    new Function('exports', 'require', code)(exports, id => {
        if (id in overrides) return overrides[id];
        if (id.startsWith('@/')) return loadModule(`auth-web/${id.slice(2)}.ts`);
        if (id.startsWith('.')) return loadModule(path.resolve(path.dirname(resolved), id + '.ts'));
        return require(id);
    });
    if (!Object.keys(overrides).length) modules.set(resolved, exports);
    return exports;
}
const { voiceDialogCopy, voiceDialogSpeakerName } = loadModule('auth-web/lib/voiceDialogLocale.ts');
const { localizedVoiceDescription } = loadModule('auth-web/lib/voiceDescriptionLocale.ts');
const nodes = n => !n || typeof n !== 'object' ? [] : Array.isArray(n) ? n.flatMap(nodes) : [n, ...nodes(n.props?.children)];
const text = n => n == null || typeof n === 'boolean' ? '' : typeof n !== 'object' ? String(n) : Array.isArray(n) ? n.map(text).join('') : text(n.props?.children);
const button = (tree, label) => {
    const found = tree.find(n => n.type === 'button' && text(n) === label);
    assert(found, `Missing button: ${label}`);
    return found;
};
const cardNames = tree => tree.filter(n => n.type === 'p' && n.props.title && n.props.className?.includes('font-bold')).map(n => text(n));
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
let calls = 0, sampleOK = true;
global.fetch = async () => { calls++; return { ok: sampleOK, blob: async () => new Blob(['sample']) }; };
global.document = { body: {}, activeElement: { focus() {} }, addEventListener() {}, removeEventListener() {} };
const storage = new Map();
global.localStorage = { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) };
const voices = [
    { id: 'eleven-1', name: 'George - Warm, Captivating Storyteller', gender: 'male', description: 'Warm resonance that instantly captivates listeners.', preview_url: 'sample.mp3' },
    { id: 'eleven-2', name: 'Sarah', gender: 'female', description: 'A confident and warm voice.', preview_url: 'sample2.mp3' },
    { id: 'google_ko', name: 'Google Korean', category: 'google' },
];
function harness(initialTab, historyUserId, speakerContext, locale = 'ko', extra = {}) {
    const state = [], refs = [], effects = [], applied = [];
    let index = 0, ri = 0, closed = 0, firstRender = true;
    const react = {
        useState: init => { const i = index++; if (!(i in state)) state[i] = typeof init === 'function' ? init() : init; return [state[i], v => { state[i] = typeof v === 'function' ? v(state[i]) : v; }]; },
        useRef: init => { const i = ri++; return refs[i] ??= { current: init }; },
        useEffect: fn => { if (firstRender) effects.push(fn); },
        useMemo: fn => fn(),
        useCallback: fn => fn,
    };
    const component = loadModule('auth-web/components/UnifiedVoiceDialog.tsx', {
        react, 'react-dom': { createPortal: x => x }, 'react/jsx-runtime': jsx,
    }).default;
    const props = { speakerContext, historyUserId, locale, value: 'gemini:Charon', initialTab,
        title: voiceDialogCopy(locale).dialogueTitle, headers: {}, voices,
        onApply: (...args) => applied.push(args), onClose: () => closed++, ...extra };
    const render = () => { index = ri = 0; const result = nodes(component(props)); firstRender = false; return result; };
    return { render, effects, refs, props, applied, get closed() { return closed; } };
}

(async () => {
    const ko = voiceDialogCopy('ko');
    // Speaker labels are presentation only: localize without changing saved identity.
    const cachedThai = Object.freeze({ name: '町奉行', label: '町奉行 (เจ้าเมือง)' });
    assert.equal(voiceDialogSpeakerName(cachedThai, 'th'), 'เจ้าเมือง');
    assert.deepEqual(cachedThai, { name: '町奉行', label: '町奉行 (เจ้าเมือง)' });
    const nativeThai = Object.freeze({ name: 'สมชาย', label: 'สมชาย' });
    assert.equal(voiceDialogSpeakerName(nativeThai, 'th'), 'สมชาย');
    const untranslated = Object.freeze({ name: '町奉行', label: '町奉行' });
    for (const locale of ['ko', 'en', 'vi', 'th']) {
        assert.equal(voiceDialogSpeakerName(untranslated, locale), voiceDialogCopy(locale).speakerNameUnavailable);
    }
    assert.deepEqual(untranslated, { name: '町奉行', label: '町奉行' });
    assert.equal(voiceDialogSpeakerName(null, 'th'), '');
    assert.equal(voiceDialogSpeakerName({ name: '홍길동', label: '홍길동' }, 'ko'), '홍길동');
    assert.equal(voiceDialogSpeakerName({ name: 'Nguyễn', label: 'Nguyễn' }, 'vi'), 'Nguyễn');
    for (const tab of ['google', 'elevenlabs']) {
        const h = harness(tab); let tree = h.render();
        assert.equal(tree.filter(n => n.props?.role === 'dialog').length, 1);
        assert.equal(text(tree.find(n => n.props?.role === 'tab' && n.props['aria-selected'])), ko[tab]);
        assert.equal(calls, 0, 'Opening a dialog must not generate samples');
        button(tree, ko.elevenlabs).props.onClick(); tree = h.render();
        assert.equal(calls, 0, 'Switching providers must not generate samples');
        assert(cardNames(tree).includes(voices[0].name));
        assert(!cardNames(tree).includes('Charon'));
        button(tree, ko.select).props.onClick(); tree = h.render();
        assert.deepEqual(h.applied, [], 'Draft selection is not applied early');
        await button(tree, ko.confirm).props.onClick();
        assert.equal(h.applied[0][0], 'eleven-1'); assert.equal(h.closed, 1);
    }
    const cancelled = harness('google'); button(cancelled.render(), ko.cancel).props.onClick();
    assert.deepEqual(cancelled.applied, []);
    let stopped = 0;
    cancelled.refs[0].current = { pause: () => stopped++ };
    const cleanup = cancelled.effects[1](); cancelled.refs[2].current = new AbortController(); cleanup();
    assert.equal(stopped, 1); assert(cancelled.refs[2].current.signal.aborted);

    // All language modes render translated controls, descriptions and errors while names remain exact.
    for (const locale of ['ko', 'en', 'vi', 'th']) {
        const copy = voiceDialogCopy(locale);
        const h = harness('elevenlabs', undefined, { name: locale === 'th' ? 'สมชาย' : 'Speaker', gender: 'male', count: 2, thai: false }, locale);
        let tree = h.render();
        assert.equal(tree.find(n => n.props?.role === 'dialog').props['aria-label'], copy.dialogueTitle);
        for (const label of [copy.close, copy.google, copy.elevenlabs, copy.all, copy.female, copy.male, copy.cancel, copy.confirm]) button(tree, label);
        assert(tree.some(n => n.props?.placeholder === copy.searchPlaceholder));
        assert.deepEqual(cardNames(tree), voices.slice(0, 2).map(v => v.name));
        assert(tree.some(n => text(n) === localizedVoiceDescription(voices[0], locale)));
        assert(!tree.some(n => n.type === 'audio' && n.props.controls), 'Native audio controls must not leak the browser language');
        assert(tree.some(n => n.props?.['aria-label'] === copy.seek));
        assert(tree.some(n => n.props?.['aria-label'] === copy.volume));
        button(tree, copy.female).props.onClick(); tree = h.render();
        assert.deepEqual(cardNames(tree), ['Sarah']);
        button(tree, copy.select).props.onClick(); tree = h.render();
        assert.equal(button(tree, copy.confirm).props.disabled, true, 'Gender mismatch must remain blocked in every locale');
        assert(tree.some(n => n.props?.role === 'alert' && text(n).includes(copy.mismatch(h.props.speakerContext.name, 'Sarah'))));
        tree.filter(n => n.type === 'input' && n.props.type === 'checkbox')[1].props.onChange({ target: { checked: true } }); tree = h.render();
        assert.equal(button(tree, copy.confirm).props.disabled, false);
        await button(tree, copy.confirm).props.onClick(); assert.equal(h.applied[0][2], true);
        // Canonical gender state survives a live locale switch, including Korean Google catalog genders.
        h.props.locale = locale === 'th' ? 'en' : 'th';
        const nextCopy = voiceDialogCopy(h.props.locale); tree = h.render();
        assert.deepEqual(cardNames(tree), ['Sarah']);
        button(tree, nextCopy.google).props.onClick(); tree = h.render();
        assert(cardNames(tree).includes('Achernar')); assert(!cardNames(tree).includes('Charon'));
        button(tree, nextCopy.male).props.onClick(); tree = h.render();
        assert(cardNames(tree).includes('Charon')); assert(!cardNames(tree).includes('Achernar'));
        button(tree, nextCopy.elevenlabs).props.onClick(); tree = h.render();
        assert.deepEqual(cardNames(tree), [voices[0].name]);
        button(tree, nextCopy.all).props.onClick(); tree = h.render();
        const description = localizedVoiceDescription(voices[0], h.props.locale);
        tree.find(n => n.props?.placeholder === nextCopy.searchPlaceholder).props.onChange({ target: { value: description } }); tree = h.render();
        assert(cardNames(tree).includes(voices[0].name), 'Localized descriptions are searchable');
        tree.find(n => n.props?.placeholder === nextCopy.searchPlaceholder).props.onChange({ target: { value: 'no-matching-voice-421' } }); tree = h.render();
        assert(tree.some(n => text(n) === nextCopy.noResults));

        const failed = harness('google', undefined, undefined, locale); let ft = failed.render();
        const beforeCalls = calls; sampleOK = false;
        button(ft, copy.preview).props.onClick(); await tick(); ft = failed.render();
        assert.equal(calls, beforeCalls + 1);
        assert(ft.some(n => n.props?.role === 'alert' && text(n) === copy.sampleFailed));
        // Saved error codes relocalize immediately if language changes while the dialog remains open.
        failed.props.locale = locale === 'th' ? 'ko' : 'th'; ft = failed.render();
        assert(ft.some(n => n.props?.role === 'alert' && text(n) === voiceDialogCopy(failed.props.locale).sampleFailed));
        sampleOK = true;
        const saveFailure = harness('elevenlabs', undefined, undefined, locale, { value: 'eleven-1', onApply: async () => { throw new Error('Raw English backend error'); } });
        await button(saveFailure.render(), copy.confirm).props.onClick();
        assert(saveFailure.render().some(n => n.props?.role === 'alert' && text(n) === copy.saveFailed));
    }
    const google = harness('google'); let plays = 0; let tree = google.render();
    google.refs[0].current = { pause() {}, play: async () => plays++ };
    const beforeCalls = calls; button(tree, ko.preview).props.onClick(); await tick();
    assert.equal(calls, beforeCalls + 1); assert.equal(plays, 1);
    const previewFailure = harness('elevenlabs', undefined, undefined, 'th'); tree = previewFailure.render();
    previewFailure.refs[0].current = { pause() {}, play: async () => { throw new Error('Browser playback error in English'); } };
    button(tree, voiceDialogCopy('th').preview).props.onClick(); await tick();
    assert(previewFailure.render().some(n => n.props?.role === 'alert' && text(n) === voiceDialogCopy('th').previewFailed));

    // A sample can begin playing before its duration is known; stopping it must remain possible.
    const streaming = harness('elevenlabs', undefined, undefined, 'th');
    const th = voiceDialogCopy('th'); let streamTree = streaming.render();
    let pauses = 0;
    streaming.refs[0].current = { pause: () => pauses++, play: async () => {} };
    const audio = streamTree.find(n => n.type === 'audio');
    audio.props.onLoadedMetadata({ currentTarget: { duration: Infinity } });
    audio.props.onPlay(); streamTree = streaming.render();
    assert.equal(button(streamTree, th.pause).props.disabled, false, 'Unknown-duration playback can be paused');
    assert.equal(streamTree.find(n => n.props?.['aria-label'] === th.seek).props.disabled, true);
    button(streamTree, th.pause).props.onClick(); assert.equal(pauses, 1);
    audio.props.onDurationChange({ currentTarget: { duration: 12.5 } });
    streamTree = streaming.render();
    const seek = streamTree.find(n => n.props?.['aria-label'] === th.seek);
    assert.equal(seek.props.max, 12.5); assert.equal(seek.props.disabled, false);
    seek.props.onChange({ target: { value: '4.2' } });
    assert.equal(streaming.refs[0].current.currentTime, 4.2);
    audio.props.onPause(); streamTree = streaming.render();
    assert.equal(button(streamTree, th.play).props.disabled, false);
    audio.props.onDurationChange({ currentTarget: { duration: NaN } }); streamTree = streaming.render();
    assert.equal(streamTree.find(n => n.props?.['aria-label'] === th.seek).props.disabled, true);

    // History stores confirmed selections only and remains account scoped.
    storage.set('air:recent-voices:v1:user-a', JSON.stringify(['eleven-2', 'eleven-1']));
    const history = harness('elevenlabs', 'user-a'); history.render(); history.effects[0]();
    let ordered = history.render(); assert.deepEqual(cardNames(ordered), ['Sarah', voices[0].name]);
    button(ordered, ko.select).props.onClick();
    assert.deepEqual(JSON.parse(storage.get('air:recent-voices:v1:user-a')), ['eleven-2', 'eleven-1']);
    await button(history.render(), ko.confirm).props.onClick();
    ordered = history.render(); ordered.filter(n => n.type === 'button' && [ko.select, ko.selected].includes(text(n)))[1].props.onClick();
    await button(history.render(), ko.confirm).props.onClick();
    const reopened = harness('elevenlabs', 'user-a'); reopened.render(); reopened.effects[0]();
    assert.deepEqual(cardNames(reopened.render()), [voices[0].name, 'Sarah']);
    const other = harness('elevenlabs', 'user-b'); other.render(); other.effects[0](); assert.deepEqual(cardNames(other.render()), [voices[0].name, 'Sarah']);
    storage.set('air:recent-voices:v1:user-a', 'invalid json');
    const corrupt = harness('elevenlabs', 'user-a'); corrupt.render(); corrupt.effects[0](); assert.deepEqual(cardNames(corrupt.render()), [voices[0].name, 'Sarah']);
    console.log('PASS: ko/en/vi/th controls, descriptions, search, errors and mismatch warnings; exact voice names; language-independent gender filters and history; explicit-only samples; localized audio controls; cleanup and cancellation');
})().catch(error => { console.error(error); process.exitCode = 1; });
