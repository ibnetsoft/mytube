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
        assert.ok(html.includes(stdUiText(locale, '성우 미지정 {missing}개 · 내레이션 성우와 겹침 {shared}개', { missing: 0, shared: 0 })));
        assert.ok(html.includes(`aria-busy="${busy}"`));
    }
}
for (const voice of ['', 'narrator']) {
    const rows = [subtitles[0], { ...subtitles[1], voice_id: voice }];
    const html = renderToStaticMarkup(React.createElement(Notice, {
        subtitles: rows, readiness: subtitleTtsReadiness(rows, row => row.dialogue, 'narrator'),
        busy: false, voices: new Map(), onJump() {},
    }));
    assert.ok(html.includes('씬 1 · 자막 2로 이동'));
    assert.ok(html.includes(voice ? '내레이션 성우와 겹침 1개' : '성우 미지정 1개'));
}
console.log('PASS: voice status stays visible after resolution and during TTS in all four locales; unresolved issues retain navigation');
