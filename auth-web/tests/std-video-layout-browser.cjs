// Exercise the real video page locally; all user data and APIs are fixtures.
const { chromium, expect } = require('@playwright/test')
const assert = require('node:assert/strict')
const path = require('node:path')
const fs = require('node:fs')
const base = process.env.STD_VIDEO_TEST_URL || 'http://127.0.0.1:3017'
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
const id = '00000000-0000-4000-8000-000000000100'
const prompt = 'Instrumental Japanese folktale background music. Soft koto and bamboo flute, restrained dynamics, no vocals.\nKeep narration clear and make the ending loop seamlessly.'
const people = Array.from({ length: 7 }, (_, i) => ({ name: `登場人物 ${i + 1}`, role: '에도 시대 인물', scene_numbers: [1, 2],
    image_url: `/api/std/projects/${id}/character-thumbnail?slot=${i}`,
    character_sheet_assets: [{ type: 'design', image_url: '/fixture/large.png' }] }))
const project = { id, title: '영상 페이지 확인', status: 'in_progress', language: 'ja',
    project_payload: { structure: { bgm_prompt: { prompt_en: prompt, description_ko: '이야기의 분위기에 맞춘 잔잔한 배경음입니다.' },
        character_anchors: { main_character: people[0], supporting_characters: people.slice(1) } } }, progress_payload: {} }
const out = process.env.STD_VIDEO_TEST_OUTPUT || 'D:/AIRStudio/maintenance/video-bgm-compact'
fs.mkdirSync(out, { recursive: true })
;(async () => {
    const browser = await chromium.launch({ channel: 'chrome', headless: true })
    const context = await browser.newContext({ viewport: { width: 1500, height: 950 }, permissions: ['clipboard-read', 'clipboard-write'] })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    try {
        await page.addInitScript(() => {
            localStorage.setItem('std_session_token', 'fixture')
            localStorage.setItem('std_current_nav', 'image_gen')
        })
        await page.route('**/*', async route => {
            const url = new URL(route.request().url())
            if (url.origin !== base) return route.abort()
            if (url.pathname.includes('/character-thumbnail')) return route.fulfill({ contentType: 'image/svg+xml', body:
                '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#558b89"/><circle cx="32" cy="26" r="15" fill="#f0cba5"/></svg>' })
            if (!url.pathname.startsWith('/api/')) return route.continue()
            let body = { success: true }
            if (url.pathname.endsWith('/me')) body = { user: { id: 'fixture', email: 'fixture@example.invalid' } }
            if (url.pathname.endsWith('/projects')) body = { projects: [project] }
            if (url.pathname === `/api/std/projects/${id}`) body = { success: true, project, scenes: [], assets: [] }
            if (url.pathname.endsWith('/voices')) body = { voices: [] }
            if (url.pathname.endsWith('/topics')) body = { topics: [] }
            return route.fulfill({ json: body })
        })
        await page.goto(`${base}/std?tab=image_gen&projectId=${id}`, { waitUntil: 'domcontentloaded' })
        await expect(page.getByRole('combobox', { name: '웹툰 자동 제작 모드', exact: true })).toHaveCount(0)
        await expect(page.getByRole('button', { name: '제작 모드 저장', exact: true })).toHaveCount(0)
        const list = page.getByRole('list', { name: '캐릭터 기준 이미지', exact: true })
        await expect(list.getByRole('img')).toHaveCount(7)
        const rects = await list.getByRole('img').evaluateAll(imgs => imgs.map(img => {
            const r = img.getBoundingClientRect(); return { width: r.width, height: r.height, top: r.top }
        }))
        assert(rects.every(r => r.width === 56 && r.height === 56 && r.top === rects[0].top))
        await expect(page.getByText('기본 디자인', { exact: true })).toHaveCount(0)
        const field = page.getByRole('textbox', { name: '배경음 생성 프롬프트', exact: true })
        await expect(field).toBeHidden()
        await page.getByRole('button', { name: '프롬프트 복사', exact: true }).click()
        await expect(page.getByRole('button', { name: '복사 완료', exact: true })).toBeVisible()
        assert.equal((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, '\n'), prompt)
        await page.locator('summary').filter({ hasText: '배경음 프롬프트' }).click()
        await expect(field).toHaveValue(prompt)
        await page.screenshot({ path: path.join(out, 'desktop.png'), fullPage: false })
        await page.setViewportSize({ width: 390, height: 844 })
        assert(await list.evaluate(el => el.scrollWidth > el.clientWidth))
        await page.screenshot({ path: path.join(out, 'mobile.png'), fullPage: false })
        delete project.project_payload.structure.bgm_prompt
        await page.reload({ waitUntil: 'domcontentloaded' })
        await expect(page.getByRole('button', { name: '프롬프트 복사', exact: true })).toBeDisabled()
        assert.deepEqual(errors, [])
        console.log('PASS: compact 56px horizontal references, exact clipboard text, prompt preview, empty state, mobile scrolling')
    } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
