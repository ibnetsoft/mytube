const assert = require('node:assert/strict');
const { chromium } = require('@playwright/test');

// Run against a local /std server. Every app API and media request is mocked;
// this must never read or mutate a real project.
const baseURL = process.env.STD_PREVIEW_TEST_URL || 'http://127.0.0.1:3016';
assert(['localhost', '127.0.0.1'].includes(new URL(baseURL).hostname), 'Use a local fixture server');
const projectId = 'e9233112-f0d7-4b35-91bf-2f892844eb30';
const rows = [
    { id: 'scene-99', scene_number: 99, text: '前の場面です。', start_time: 793.3, end_time: 795 },
    { id: 'scene-100-first', scene_number: 100, text: '新しい場面です。', start_time: 793.8, end_time: 800 },
    { id: 'scene-100-second', scene_number: 100, text: '同じ場面の続きです。', start_time: 800, end_time: 823.7 },
    { id: 'scene-101', scene_number: 101, text: '最後の場面です。', start_time: 823.7, end_time: 827.1 },
].map(row => ({ ...row, start_num: row.start_time, end_num: row.end_time, translation_manual: true }));
const scenes = [99, 100, 101].map((sceneNumber, index) => ({
    scene_number: sceneNumber,
    image_url: `/preview-fixture/scene-${sceneNumber}.svg`,
    video_url: sceneNumber === 100 ? '/preview-fixture/slow-scene-100.webm' : null,
    scene_text: rows.find(row => row.scene_number === sceneNumber).text,
    start_seconds: [793.3, 793.8, 823.7][index],
    end_seconds: [795, 823.7, 827.1][index],
    duration_seconds: [1.7, 29.9, 3.4][index],
    metadata: { transition_effect: 'fade' },
}));
const project = {
    id: projectId,
    title: 'Subtitle preview fixture',
    status: 'in_progress',
    language: 'ja',
    project_payload: { subtitles: rows },
    progress_payload: {},
};

(async () => {
    const browser = await chromium.launch({ headless: true, channel: process.env.STD_PREVIEW_BROWSER_CHANNEL || undefined });
    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
    const failures = [];
    const stalledVideos = [];
    const externalRequests = [];
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    try {
        await page.addInitScript(() => {
            localStorage.setItem('std_session_token', 'fixture');
            localStorage.setItem('std_current_nav', 'subtitle_vrew');
        });
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== new URL(baseURL).origin) {
                externalRequests.push(url.origin);
                return route.abort();
            }
            const pathname = url.pathname;
            if (pathname.startsWith('/preview-fixture/')) {
                if (pathname.endsWith('.webm')) {
                    // Deliberately never reach loadeddata until explicitly released.
                    // The selected image must show without waiting for this video.
                    stalledVideos.push(route);
                    return;
                }
                const sceneNumber = Number(pathname.match(/scene-(\d+)/)?.[1]);
                const colors = { 99: '#9b2727', 100: '#197b4b', 101: '#27469b' };
                return route.fulfill({ contentType: 'image/svg+xml', body:
                    `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="${colors[sceneNumber]}"/><text x="40" y="80" font-size="48" fill="white">Scene ${sceneNumber}</text></svg>` });
            }
            if (pathname.startsWith('/api/')) {
                let body = { success: true };
                if (pathname.endsWith('/me')) body = { user: { id: 'fixture', email: 'fixture@example.invalid', full_name: 'fixture' } };
                if (pathname.endsWith('/projects')) body = { projects: [project] };
                if (pathname === `/api/std/projects/${projectId}`) body = { project, scenes, assets: [] };
                if (pathname.endsWith('/speaker-coordinates')) body = { state: 'complete', count: 0, results: [] };
                if (pathname.endsWith('/topics')) body = { topics: [] };
                if (pathname.endsWith('/voices')) body = { voices: [] };
                return route.fulfill({ json: body });
            }
            return route.continue();
        });

        await page.goto(`${baseURL}/std?tab=subtitle_vrew&projectId=${projectId}`, { waitUntil: 'domcontentloaded' });
        const canvas = page.locator('.std-subtitle-preview .aspect-video').first();
        await canvas.waitFor({ state: 'visible', timeout: 30000 });
        await page.getByText('Scene 100', { exact: true }).waitFor();

        const clickScene = number => page.getByText(`Scene ${number}`, { exact: true }).click();
        const subtitleRows = page.locator('[title="클릭하여 선택 · Shift+클릭으로 연속된 자막 선택"]');
        const clickRow = (id, options) => subtitleRows.filter({ hasText: rows.find(row => row.id === id).text }).click(options);
        async function expectScene(number, rowId, delay = 150) {
            await page.waitForTimeout(delay);
            const state = await canvas.evaluate(element => ({
                background: element.style.backgroundImage,
                text: element.textContent,
                overlays: element.querySelectorAll(':scope > .absolute.z-10').length,
                image: element.querySelector('img[alt="Preview"]')?.getAttribute('src'),
                video: element.querySelector('video')?.getAttribute('src'),
            }));
            assert(state.background.includes(`/scene-${number}.svg`), `Scene ${number}: wrong background ${JSON.stringify(state)}`);
            assert(state.text.includes(rows.find(row => row.id === rowId).text), `Scene ${number}: wrong subtitle ${JSON.stringify(state)}`);
            assert.equal(state.overlays, 0, `Scene ${number}: previous visual still covers selected scene`);
            if (number === 100) assert(state.video?.endsWith('/slow-scene-100.webm'), 'The selected video is attached');
            else assert(state.image?.endsWith(`/scene-${number}.svg`), 'The selected image is attached');
        }
        async function check(name, run) {
            try { await run(); console.log(`PASS: ${name}`); }
            catch (error) { failures.push(`${name}: ${error.message}`); console.error(`FAIL: ${name}: ${error.message}`); }
        }

        await check('scene-card click preserves explicit selection across overlapping times', async () => {
            await clickScene(99);
            await clickScene(100);
            await expectScene(100, 'scene-100-first');
            await expectScene(100, 'scene-100-first', 700);
        });
        await check('subtitle-row click preserves explicit selection across overlapping times', async () => {
            await clickScene(99);
            await clickRow('scene-100-first');
            await expectScene(100, 'scene-100-first');
        });
        await check('stalled video immediately reveals selected scene poster', async () => {
            await clickScene(99);
            await clickRow('scene-100-second');
            await expectScene(100, 'scene-100-second');
            await expectScene(100, 'scene-100-second', 800);
        });
        await check('rapid image/video selections remain on the last clicked scene', async () => {
            for (const id of ['scene-100-second', 'scene-101', 'scene-99', 'scene-100-second', 'scene-101']) {
                await clickRow(id);
            }
            await expectScene(101, 'scene-101');
            await expectScene(101, 'scene-101', 800);
        });
        await check('late video failure cannot replace a later image selection', async () => {
            assert(stalledVideos.length > 0, 'Slow video was requested');
            await clickRow('scene-100-second');
            await clickScene(101);
            await Promise.all(stalledVideos.splice(0).map(route => route.fulfill({ status: 503, body: 'Fixture video delayed failure' }).catch(() => {})));
            await expectScene(101, 'scene-101', 800);
        });
        await check('paused timeline seeking still selects the subtitle at the requested time', async () => {
            const seekbar = page.locator('.std-subtitle-preview div[class*="bg-gray-700"][class*="cursor-pointer"]');
            const rect = await seekbar.boundingBox();
            assert(rect, 'Preview seek bar is visible');
            // Use a wide interval; a single screen pixel spans >1 second here.
            await seekbar.click({ position: { x: rect.width * 810 / 827.1, y: rect.height / 2 } });
            await expectScene(100, 'scene-100-second');
        });
        await check('Shift selection still selects a contiguous range within the scene', async () => {
            await clickRow('scene-100-first');
            await clickRow('scene-100-second', { modifiers: ['Shift'] });
            await expectScene(100, 'scene-100-second');
            const selectedTexts = await subtitleRows.evaluateAll(elements => elements
                .filter(element => element.className.includes('border-cyan-400/60')).map(element => element.textContent));
            assert.equal(selectedTexts.length, 2, 'Both rows in the shift-selected range remain selected');
            assert(selectedTexts.every(text => text.includes(rows[1].text) || text.includes(rows[2].text)), 'Only scene 100 is selected');
        });
        assert.deepEqual(pageErrors, [], 'The full page renders without uncaught browser errors');
        assert.deepEqual(externalRequests, [], 'The fixture never needs a real external service');
        assert.deepEqual(failures, [], 'Subtitle preview regression checks');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
