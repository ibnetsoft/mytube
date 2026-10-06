const assert = require('node:assert/strict');
const fs = require('fs');
const ts = require('typescript');
const { chromium } = require('@playwright/test');
function load(filename) {
    const exports = {};
    new Function('exports', ts.transpile(fs.readFileSync(filename, 'utf8'), { module: 1, target: 7 }))(exports);
    return exports;
}
// Run from the repository root against a local server. All application APIs and
// media are mocked, including writes. Never use a real project or remote server.
const baseURL = process.env.STD_VOICE_TEST_URL || 'http://127.0.0.1:3016';
assert(['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname), 'Use a local fixture server');
const { voiceDialogCopy, voiceDialogSpeakerName } = load('auth-web/lib/voiceDialogLocale.ts');
const { localizedVoiceDescription } = load('auth-web/lib/voiceDescriptionLocale.ts');
const { VOICE_STUDIO_VOICES } = load('auth-web/lib/voiceStudioCatalog.ts');
const projectId = 'e9233112-f0d7-4b35-91bf-2f892844eb30';
const voices = [
    { id: 'fixture-george', name: 'George - Warm, Captivating Storyteller', gender: 'male', description: 'Warm resonance that instantly captivates listeners.', preview_url: '/voice-fixture/sample.mp3' },
    { id: 'fixture-sarah', name: 'Sarah', gender: 'female', description: 'Young adult woman with a confident and warm, mature quality and a reassuring, professional tone.', preview_url: '/voice-fixture/sample.mp3' },
    { id: 'fixture-unknown', name: 'Custom Name', gender: 'neutral', description: 'An unlisted English description with unique foreign words.', preview_url: '/voice-fixture/sample.mp3' },
];
const rows = [
    { id: 'dialogue-1', text: '「こんにちは。」', start_time: 0, end_time: 4, dialogue_override: true, voice_id: voices[0].id },
    { id: 'dialogue-2', text: '「ありがとうございます。」', start_time: 4, end_time: 8, dialogue_override: true, voice_id: voices[0].id },
    { id: 'narration-1', text: '静かな朝でした。', start_time: 8, end_time: 12, dialogue_override: false, voice_id: 'gemini:Charon' },
].map(row => ({ ...row, scene_number: 1, start_num: row.start_time, end_num: row.end_time, translation_manual: true,
    ...(row.dialogue_override ? { dialogue_speaker: 'สมชาย', editor_speaker: { name: 'สมชาย', gender: 'male', text: row.text } } : {}) }));
const project = { id: projectId, title: 'Voice localization fixture', status: 'in_progress', language: 'ja', project_payload: { subtitles: rows }, progress_payload: {} };
const scenes = [{ scene_number: 1, image_url: '/voice-fixture/scene.svg', scene_text: rows.map(row => row.text).join(' '), start_seconds: 0, end_seconds: 12, duration_seconds: 12 }];

(async () => {
    const browser = await chromium.launch({ headless: true, channel: process.env.STD_VOICE_BROWSER_CHANNEL || undefined });
    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
    const pageErrors = [], externalRequests = [];
    let sampleRequests = 0;
    page.on('pageerror', error => pageErrors.push(error.message));
    try {
        await page.addInitScript(() => {
            localStorage.setItem('std_session_token', 'fixture');
            localStorage.setItem('std_current_nav', 'subtitle_vrew');
        });
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== new URL(baseURL).origin) { externalRequests.push(url.origin); return route.abort(); }
            if (url.pathname === '/voice-fixture/scene.svg') return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#197b4b"/></svg>' });
            if (url.pathname === '/voice-fixture/sample.mp3') return route.fulfill({ status: 503, body: 'Audio fixture failure' });
            if (url.pathname.startsWith('/api/')) {
                let body = { success: true };
                if (url.pathname.endsWith('/me')) body = { user: { id: 'voice-fixture', email: 'fixture@example.invalid', full_name: 'fixture' } };
                if (url.pathname.endsWith('/projects')) body = { projects: [project] };
                if (url.pathname === `/api/std/projects/${projectId}`) body = { project, scenes, assets: [] };
                if (url.pathname.endsWith('/speaker-coordinates')) body = { state: 'complete', count: 0, results: [] };
                if (url.pathname.endsWith('/topics')) body = { topics: [] };
                if (url.pathname.endsWith('/voices')) body = { voices };
                if (url.pathname.endsWith('/voice-studio/sample')) { sampleRequests++; return route.fulfill({ status: 503, json: { error: 'English backend failure must not leak' } }); }
                return route.fulfill({ json: body });
            }
            return route.continue();
        });
        await page.goto(`${baseURL}/std?tab=subtitle_vrew&projectId=${projectId}`, { waitUntil: 'domcontentloaded' });
        const row = page.locator('[title="클릭하여 선택 · Shift+클릭으로 연속된 자막 선택"]').filter({ hasText: rows[0].text });
        await row.waitFor({ state: 'visible', timeout: 30000 });
        const languageLabels = { ko: '한국어', en: 'English', vi: 'Tiếng Việt', th: 'ภาษาไทย' };
        const getDialog = () => page.getByRole('dialog');
        async function assertNoForeignThaiCopy(dialog) {
            const copy = await dialog.evaluate(element => [element.textContent,
                ...Array.from(element.querySelectorAll('[aria-label], [placeholder], [title]')).flatMap(node => ['aria-label', 'placeholder', 'title'].map(attribute => node.getAttribute(attribute) || ''))].join('\n'));
            const allowedNames = [...voices, ...VOICE_STUDIO_VOICES].map(voice => voice.name).sort((a, b) => b.length - a.length);
            const withoutNames = allowedNames.reduce((result, name) => result.split(name).join(''), copy);
            assert(!/[A-Za-z가-힣]/.test(withoutNames), `Thai popup leaked foreign UI copy: ${withoutNames}`);
        }
        for (const locale of ['ko', 'en', 'vi', 'th']) {
            const copy = voiceDialogCopy(locale);
            await page.getByRole('button', { name: languageLabels[locale], exact: true }).click();
            await row.locator('button[title^="ElevenLabs"]').click();
            const dialog = getDialog(); await dialog.waitFor();
            assert.equal(await dialog.getAttribute('aria-label'), copy.dialogueTitle);
            assert.equal(await dialog.getByRole('tab', { name: copy.elevenlabs, exact: true }).getAttribute('aria-selected'), 'true');
            await dialog.getByText(voices[0].name, { exact: true }).waitFor();
            await dialog.getByText(localizedVoiceDescription(voices[0], locale), { exact: true }).waitFor();
            assert.equal(await dialog.locator('audio[controls]').count(), 0);
            await dialog.getByRole('slider', { name: copy.seek, exact: true }).waitFor();
            await dialog.getByRole('slider', { name: copy.volume, exact: true }).waitFor();
            if (locale === 'th') {
                await assertNoForeignThaiCopy(dialog);
                if (process.env.STD_VOICE_SCREENSHOT) await page.screenshot({ path: process.env.STD_VOICE_SCREENSHOT });
                await page.setViewportSize({ width: 390, height: 844 });
                const bounds = await dialog.boundingBox();
                assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 391, 'Mobile dialog fits the viewport');
                const overflow = await dialog.evaluate(element => element.scrollWidth > element.clientWidth + 1);
                assert.equal(overflow, false, 'Mobile popup has no horizontal overflow');
                const confirmBounds = await dialog.getByRole('button', { name: copy.confirm, exact: true }).boundingBox();
                assert(confirmBounds && confirmBounds.y + confirmBounds.height <= 844, 'Mobile confirmation remains visible');
                await assertNoForeignThaiCopy(dialog);
                if (process.env.STD_VOICE_SCREENSHOT) await page.screenshot({ path: process.env.STD_VOICE_SCREENSHOT.replace(/\.png$/, '-mobile.png') });
                await page.setViewportSize({ width: 1500, height: 1000 });
                console.log('PASS: Thai mobile popup fits 390px viewport with visible confirmation and translated copy');
            }
            await dialog.getByRole('button', { name: copy.female, exact: true }).click();
            await dialog.getByText('Sarah', { exact: true }).waitFor();
            assert.equal(await dialog.getByText(voices[0].name, { exact: true }).count(), 0);
            await dialog.getByRole('button', { name: copy.select, exact: true }).click();
            assert.equal(await dialog.getByRole('button', { name: copy.confirm, exact: true }).isDisabled(), true);
            await dialog.getByRole('alert').getByText(copy.mismatch(voiceDialogSpeakerName({ name: 'สมชาย', label: 'สมชาย' }, locale), 'Sarah'), { exact: true }).waitFor();
            await dialog.getByLabel(copy.allowMismatch, { exact: true }).check();
            assert.equal(await dialog.getByRole('button', { name: copy.confirm, exact: true }).isEnabled(), true);
            await dialog.getByRole('tab', { name: copy.google, exact: true }).click();
            await dialog.getByText('Achernar', { exact: true }).waitFor();
            assert.equal(await dialog.getByText('Charon', { exact: true }).count(), 0);
            await dialog.getByRole('button', { name: copy.all, exact: true }).click();
            await dialog.getByText('Charon', { exact: true }).waitFor();
            if (locale === 'th') await assertNoForeignThaiCopy(dialog);
            await dialog.getByRole('tab', { name: copy.elevenlabs, exact: true }).click();
            await dialog.getByPlaceholder(copy.searchPlaceholder).fill(localizedVoiceDescription(voices[0], locale));
            await dialog.getByText(voices[0].name, { exact: true }).waitFor();
            await dialog.getByPlaceholder(copy.searchPlaceholder).fill('no-matching-voice-421');
            await dialog.getByText(copy.noResults, { exact: true }).waitFor();
            await dialog.getByRole('button', { name: copy.cancel, exact: true }).click();
            await dialog.waitFor({ state: 'hidden' });
            assert.equal(sampleRequests, 0, 'Opening, switching and filtering never generate paid samples');
            console.log(`PASS: ${locale} dialogue title, description, filters, mismatch, provider switch, search and localized controls`);
        }
        // Also verify the separate narration picker forwards the language mode.
        const th = voiceDialogCopy('th');
        await page.getByRole('button', { name: '씬 1 Google 내레이션 성우 선택', exact: true }).click();
        let dialog = getDialog(); await dialog.waitFor();
        assert.equal(await dialog.getAttribute('aria-label'), th.narrationTitle);
        await dialog.getByText(th.sceneScope, { exact: true }).waitFor();
        await dialog.getByPlaceholder(th.directionPlaceholder).waitFor();
        await assertNoForeignThaiCopy(dialog);
        await dialog.getByRole('button', { name: th.preview, exact: true }).first().click();
        await dialog.getByRole('alert').getByText(th.sampleFailed, { exact: true }).waitFor();
        assert.equal(sampleRequests, 1);
        await assertNoForeignThaiCopy(dialog);
        await dialog.getByRole('button', { name: th.close, exact: true }).click();
        console.log('PASS: Thai narration picker, direction field, sample notice and explicit sample failure');
        assert.deepEqual(pageErrors, [], 'No uncaught browser errors');
        assert.deepEqual(externalRequests, [], 'Fixture never calls a real external service');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
