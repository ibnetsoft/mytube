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
