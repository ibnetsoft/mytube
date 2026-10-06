// Run against a local production build. API and audio fixtures never reach live services.
const { chromium, expect } = require('@playwright/test');
const assert = require('node:assert/strict');
const base = process.env.STD_BGM_TEST_URL || 'http://127.0.0.1:3016', id = '00000000-0000-4000-8000-000000000100';
assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'Use a local fixture server');
const subs = [{ id: 'one', scene_number: 100, text: '最初の場面。', start_num: 793.8, end_num: 823.7 }, { id: 'two', scene_number: 101, text: '最後の場面。', start_num: 823.7, end_num: 827.1 }].map(s => ({ ...s, start_time: s.start_num, end_time: s.end_num, translation_manual: true }));
let project = { id, title: 'BGM save fixture', status: 'in_progress', language: 'ja', project_payload: { subtitles: subs, render_settings: { bgm_asset_id: 'bgm', bgm_file_name: 'music.wav', bgm_start_scene: 100, bgm_end_scene: 101, bgm_fade_in: 4, bgm_fade_out: 0, bgm_loop: false, bgm_volume: .4 } }, progress_payload: {} };
const assets = [{ id: 'bgm', asset_type: 'other', file_name: 'music.wav', status: 'uploaded', metadata: { audio_role: 'bgm', gcs_public_url: base + '/fixture/music.wav' } }];
const scenes = subs.map(s => ({ scene_number: s.scene_number, scene_text: s.text, image_url: '/fixture/image.svg', start_seconds: s.start_num, end_seconds: s.end_num, duration_seconds: s.end_num - s.start_num }));
const wav = Buffer.alloc(44 + 8000 * 30 * 2);
wav.write('RIFF');
wav.writeUInt32LE(wav.length - 8, 4);
wav.write('WAVEfmt ', 8);
wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20);
wav.writeUInt16LE(1, 22);
wav.writeUInt32LE(8000, 24);
wav.writeUInt32LE(16000, 28);
wav.writeUInt16LE(2, 32);
wav.writeUInt16LE(16, 34);
wav.write('data', 36);
wav.writeUInt32LE(wav.length - 44, 40);
const narration = Buffer.from(wav.subarray(0, 44 + 8000 * 8 * 2));
narration.writeUInt32LE(narration.length - 8, 4);
narration.writeUInt32LE(narration.length - 44, 40);
(async () => {
    const browser = await chromium.launch({ channel: 'chrome', headless: true });
    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    try {
        await page.addInitScript(() => { localStorage.setItem('std_session_token', 'fixture'); localStorage.setItem('std_current_nav', 'subtitle_vrew'); });
        await page.route('**/*', async route => {
            const u = new URL(route.request().url());
            if (u.origin !== base) return route.abort();
            if (u.pathname === '/fixture/narration.wav') return route.fulfill({ contentType: 'audio/wav', body: narration });
            if (u.pathname === '/fixture/music.wav') return route.fulfill({ contentType: 'audio/wav', body: wav });
            if (u.pathname === '/fixture/image.svg') return route.fulfill({
                contentType: 'image/svg+xml',
                body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="green"/></svg>',
            });
            if (!u.pathname.startsWith('/api/')) return route.continue();
            let body = { success: true };
            if (u.pathname.endsWith('/me')) body = { user: { id: 'fixture', email: 'fixture@example.invalid' } };
            if (u.pathname.endsWith('/projects')) body = { projects: [project] };
            if (u.pathname === `/api/std/projects/${id}`) {
                if (route.request().method() === 'PATCH') {
                    const p = route.request().postDataJSON();
                    const audioKeys = ['bgm_asset_id', 'bgm_file_name', 'bgm_volume', 'bgm_loop', 'bgm_start_scene', 'bgm_start_subtitle', 'bgm_end_scene', 'bgm_fade_in', 'bgm_fade_out', 'sfx_cues', 'sfx_plan'];
                    const incoming = p.project_payload || {}, rs = incoming.render_settings || {};
                    const allowed = Object.fromEntries(Object.entries(rs).filter(([k]) => p.render_settings_scope === 'audio' ? audioKeys.includes(k) : !audioKeys.includes(k)));
                    project = { ...project, project_payload: { ...project.project_payload, ...incoming, render_settings: { ...project.project_payload.render_settings, ...allowed } } };
                }
                body = { success: true, project, scenes, assets };
            }
            if (u.pathname.endsWith('/voices')) body = { voices: [] };
            if (u.pathname.endsWith('/topics')) body = { topics: [] };
            if (u.pathname.endsWith('/speaker-coordinates')) body = { state: 'complete', count: 0, results: [] };
            return route.fulfill({ json: body });
        });
        async function open() {
            await page.goto(`${base}/std?tab=subtitle_vrew&projectId=${id}`, { waitUntil: 'domcontentloaded' });
            await page.getByRole('button', { name: '배경음/효과음', exact: true }).click();
            await page.waitForFunction(() => Number.isFinite(document.querySelector('.std-subtitle-preview audio')?.duration));
        }
        await open();
        const panel = page.locator('.std-subtitle-preview');
        const input = page.getByRole('spinbutton', { name: '배경음 페이드 아웃' });
        await input.fill('4');
        await input.press('Tab');
        await panel.getByRole('button', { name: '저장', exact: true }).click();
        await expect.poll(() => project.project_payload.render_settings.bgm_fade_out).toBe(4);
        await page.reload();
        await page.getByRole('button', { name: '배경음/효과음', exact: true }).click();
        await page.waitForFunction(() => Number.isFinite(document.querySelector('.std-subtitle-preview audio')?.duration));
        await expect(input).toHaveValue('4');
        const seek = panel.locator('div[class*="bg-gray-700"][class*="cursor-pointer"]');
        async function verify(time, end, fade) {
            await seek.evaluate((el, time) => {
                const r = el.getBoundingClientRect();
                const event = new MouseEvent('click', { bubbles: true, clientY: r.top + 2 });
                // MouseEvent rounds clientX; keep fractional pixels for exact timeline seeks.
                Object.defineProperty(event, 'clientX', { value: r.left + r.width * time / 827.1 });
                el.dispatchEvent(event);
            }, time);
            await expect.poll(async () => {
                const position = await seek.evaluate(el => parseFloat(el.firstElementChild.style.width) * 827.1 / 100);
                if (Math.abs(position - time) > .001)
                    return 1;
                const expected = position >= end ? 0 : .4 * Math.min(1, (end - position) / fade);
                const actual = await panel.locator('audio').first().evaluate(a => a.volume);
                return Math.abs(actual - expected);
            }).toBeLessThan(.0001);
            console.log('PASS gain', time, await panel.locator('audio').first().evaluate(a => a.volume));
        }
        for (const time of [819, 821, 824])
            await verify(time, 823.8, 4);
        await page.getByRole('checkbox', { name: '배경음 반복' }).check();
        await verify(821, 827.1, 4);
        await page.getByRole('checkbox', { name: '배경음 반복' }).uncheck();
        await input.fill('8');
        await input.press('Tab');
        await verify(821, 823.8, 8);
        await panel.getByRole('button', { name: '저장', exact: true }).click();
        await expect.poll(() => project.project_payload.render_settings.bgm_fade_out).toBe(8);
        // Real media playback over a scene boundary, starting at subtitle 2.
        subs.splice(0, subs.length, ...[
            {id:'a',scene_number:100,text:'最初の字幕。',start_num:0,end_num:2},
            {id:'b',scene_number:100,text:'音楽はここから。',start_num:2,end_num:4},
            {id:'c',scene_number:101,text:'次の場面でも続きます。',start_num:4,end_num:8},
        ].map(row=>({...row,start_time:row.start_num,end_time:row.end_num,voice_id:'fixture-voice',translation_manual:true})));
        scenes.splice(0,scenes.length,...[100,101].map(number=>({scene_number:number,scene_text:subs.find(row=>row.scene_number===number).text,
            image_url:'/fixture/image.svg',start_seconds:number===100?0:4,end_seconds:number===100?4:8,duration_seconds:4})));
        project.project_payload.subtitles=subs;
        Object.assign(project.project_payload.render_settings,{bgm_start_scene:100,bgm_start_subtitle:1,bgm_end_scene:101,bgm_fade_in:0,bgm_fade_out:0,bgm_loop:false});
        assets.push({id:'narration',asset_type:'audio',status:'uploaded',file_name:'narration.wav',metadata:{gcs_public_url:base+'/fixture/narration.wav',
            subtitle_timeline:subs.map(row=>({text:row.text,start:row.start_num,end:row.end_num,voice_id:row.voice_id}))}});
        await page.reload();
        await page.getByRole('button',{name:'배경음/효과음',exact:true}).click();
        const cue=page.getByRole('combobox',{name:'배경음 시작 자막',exact:true});
        await expect(cue.locator('option')).toHaveCount(2);
        await expect(cue.locator('option').nth(1)).toContainText('音楽はここから。');
        await cue.selectOption('2');
        await panel.getByRole('button',{name:'저장',exact:true}).click();
        await expect.poll(()=>project.project_payload.render_settings.bgm_start_subtitle).toBe(2);
        await page.reload();
        await page.getByRole('button',{name:'배경음/효과음',exact:true}).click();
        await expect(cue).toHaveValue('2');
        await page.waitForFunction(()=>Number.isFinite(document.querySelector('.std-subtitle-preview audio')?.duration));
        const music=panel.locator('audio').first();
        await expect.poll(()=>music.evaluate(a=>a.volume)).toBe(0);
        const originalMusic=await music.elementHandle();
        await panel.getByTitle('현재 자막부터 연속 미리듣기',{exact:true}).click();
        await expect.poll(()=>music.evaluate(a=>!a.paused && a.currentTime>2.5),{timeout:12000}).toBe(true);
        const continued=await music.evaluate(a=>({offset:a.currentTime,volume:a.volume}));
        assert(continued.offset>2.5 && continued.offset<6,'music must keep its position after entering scene 101');
        assert.equal(continued.volume,.4);
        assert(await originalMusic.evaluate(a=>a===document.querySelector('.std-subtitle-preview audio')),'scene changes must retain the playing audio element');
        await panel.getByTitle('자막 미리듣기 정지',{exact:true}).click();
        await expect.poll(()=>music.evaluate(a=>a.paused)).toBe(true);
        await page.getByRole('combobox',{name:'배경음 시작 씬',exact:true}).selectOption('101');
        await expect(cue).toHaveValue('1');
        await expect(cue.locator('option')).toHaveCount(1);
        await page.getByRole('combobox',{name:'배경음 시작 씬',exact:true}).selectOption('0');
        await expect(cue).toBeDisabled();
        console.log('PASS: start subtitle choices/save/reload, silence before cue, actual next-scene continuity and scene-change reset');
        assert.deepEqual(errors, []);
        console.log('PASS: edit, save, reload, one-shot fade, looping fade and live setting change');
    }
    finally {
        await browser.close();
    }
})().catch(e => { console.error(e); process.exitCode = 1; });
