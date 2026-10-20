const assert = require('node:assert/strict');
const React = require('../node_modules/react');
const { renderToStaticMarkup } = require('../node_modules/react-dom/server');
const load = require('./load-ts-module.cjs');
const Notice = load('auth-web/components/StdTtsReadinessNotice.tsx').default;
const { subtitleTtsReadiness } = load('auth-web/lib/stdTtsReadiness.ts');
const { stdUiText } = load('auth-web/lib/stdUiText.ts');
const subtitles = [
    { scene_number: 1, text: 'Narration', voice_id: 'narrator' },
    { scene_number: 1, text: 'Dialogue', voice_id: 'character', dialogue: true },
];
for (const locale of ['ko', 'en', 'vi', 'th']) {
    for (const busy of [false, true]) {
        const readiness = subtitleTtsReadiness(subtitles, row => row.dialogue, 'narrator');
        const html = renderToStaticMarkup(React.createElement(Notice, {
            subtitles, readiness, busy, locale, compact: true, voices: new Map(), onJump() {},
        }));
        assert.ok(html.includes(stdUiText(locale, '성우 미지정 대사 {missing}개 · 내레이션과 같은 성우를 쓰는 대사 {shared}개', { missing: 0, shared: 0 })));
        assert.ok(html.includes(`aria-busy="${busy}"`));
    }
    const rows = [subtitles[0], { ...subtitles[1], voice_id: 'narrator' }];
    const html = renderToStaticMarkup(React.createElement(Notice, {
        subtitles: rows, readiness: subtitleTtsReadiness(rows, row => row.dialogue, 'narrator'),
        busy: false, locale, voices: new Map(), onJump() {},
    }));
    assert.ok(html.includes(stdUiText(locale, '같은 성우를 쓰는 내레이션 위치 {count}개 보기', { count: 1 })));
    assert.match(html, /<details class="mt-1 text-gray-400">/);
    if (locale !== 'ko') assert.ok(!/[가-힣]/.test(html), `Untranslated notice in ${locale}`);
}
for (const voice of ['', 'narrator']) {
    const rows = [subtitles[0], { ...subtitles[1], voice_id: voice }];
    const html = renderToStaticMarkup(React.createElement(Notice, {
        subtitles: rows, readiness: subtitleTtsReadiness(rows, row => row.dialogue, 'narrator'),
        busy: false, voices: new Map(), onJump() {},
    }));
    assert.ok(html.includes('씬 1 · 자막 2로 이동'));
    if (voice) {
        assert.match(html, /<details class="mt-1 text-gray-400">/);
        assert.ok(html.includes('같은 성우를 쓰는 내레이션 위치 1개 보기'));
    }
    assert.ok(html.includes(voice ? '내레이션과 같은 성우를 쓰는 대사 1개' : '성우 미지정 대사 1개'));
}
console.log('PASS: voice status stays visible after resolution and during TTS in all four locales; unresolved issues retain navigation');
const { missingSpeakerSubtitleIndexes, subtitleSpeakerProgress } = load('auth-web/lib/stdSubtitleSpeakerProgress.ts');
const rows = [
    { scene_number: 49, text: 'Narration', dialogue_override: false },
    { scene_number: 49, text: 'Unassigned line', dialogue_override: true, voice_id: 'character' },
    { scene_number: 50, text: 'Confirmed line', dialogue_override: true },
    { scene_number: 51, text: 'Annotated line', voice_id: 'character' },
];
const parts = new Map([[3, [{ dialogue: true }]]]);
const speakers = [null, null, { name: 'A' }, null];
const indexes = missingSpeakerSubtitleIndexes(rows, parts, speakers);
assert.deepEqual(indexes, [1, 3]);
const progress = subtitleSpeakerProgress(rows, parts, speakers);
assert.equal(progress.total - progress.confirmed, indexes.length);
for (const locale of ['ko', 'en', 'vi', 'th']) {
    const props = { subtitles: rows, missingSpeakerIndexes: indexes, readiness: { issues: [] }, busy: false, locale, voices: new Map(), onJump() {} };
    const html = renderToStaticMarkup(React.createElement(Notice, props));
    assert.ok(html.includes(stdUiText(locale, '화자 미지정 대사 {count}개', { count: 2 })));
    assert.ok(html.includes(stdUiText(locale, '씬 {scene} · 자막 {subtitle}', { scene: 49, subtitle: 2 })));
    assert.ok(html.includes('Unassigned line'));
    if (locale !== 'ko') assert.ok(!/[가-힣]/.test(html));
}
const clicked = [];
function clickAnchors(node) {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'button') node.props.onClick();
    React.Children.forEach(node.props?.children, clickAnchors);
}
clickAnchors(Notice({ subtitles: rows, missingSpeakerIndexes: indexes, readiness: { issues: [] }, busy: false, voices: new Map(), onJump: index => clicked.push(index) }));
assert.deepEqual(clicked, [1, 3]);
assert.deepEqual(missingSpeakerSubtitleIndexes(rows, parts, [null, { name: 'B' }, { name: 'A' }, { name: 'C' }]), []);
console.log('PASS: speaker anchors match progress, retain exact subtitle indexes, and disappear after assignment');
