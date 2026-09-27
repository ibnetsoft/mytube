const { chromium } = require('@playwright/test')
const assert = require('node:assert/strict')
const path = require('node:path')
;(async () => {
    const browser = await chromium.launch({ headless: true })
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
        const errors = []; page.on('pageerror', e => errors.push(e.message))
        let submitted, items = []
        await page.addInitScript(() => { localStorage.setItem('std_session_token', 'test-session'); localStorage.setItem('std_current_nav', 'topic_submissions') })
        await page.route('**/api/std/**', async route => {
            const pathname = new URL(route.request().url()).pathname
            let body = { success: true }
            if (pathname === '/api/std/me') body = { user: { email: 'test@example.invalid', full_name: '테스트 사용자', preferred_category_ids: [2] } }
            if (pathname === '/api/std/topics') body = { topics: [] }
            if (pathname === '/api/std/projects') body = { projects: [] }
            if (pathname === '/api/std/voices') body = { voices: [] }
            if (pathname === '/api/std/topic-submissions') {
                if (route.request().method() === 'POST') {
                    submitted = route.request().postDataJSON()
                    assert(route.request().headers()['idempotency-key'])
                    items = [{ id: 'test', title: submitted.title, status: 'pending', created_at: new Date().toISOString() }]
                    body = { id: 'test' }
                } else body = { items }
            }
            await route.fulfill({ json: body })
        })
        await page.goto('http://localhost:3000/std?tab=topic_submissions')
        await page.getByRole('heading', { name: '토픽 등록', exact: true }).waitFor()
        await page.getByRole('radio', { name: /로컬 전달/ }).isChecked().then(checked => assert.equal(checked, true))
        await page.getByText('씬별 웹 미리보기나 다른 PC의 워커로 인계할 때 사용합니다.').waitFor()
        await page.locator('[name=title]').fill('편지에 담긴 약속')
        await page.locator('[name=story]').fill('오래된 편지를 발견한 주인공이 가족과 화해하는 이야기')
        await page.locator('[name=character_notes]').fill('주인공: 조용하지만 의지가 강한 인물')
        await page.locator('[name=images]').setInputFiles({ name: 'hero.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1cAAAAASUVORK5CYII=', 'base64') })
        await page.getByRole('button', { name: '토픽 등록 · 승인 요청' }).click()
        await page.getByRole('status').filter({ hasText: '토픽을 등록했습니다' }).waitFor()
        assert.equal(submitted.character_images.length, 1)
        assert.equal(submitted.ae_scene_delivery, 'local')
        assert.equal(submitted.story, '오래된 편지를 발견한 주인공이 가족과 화해하는 이야기')
        await page.getByText('승인 대기', { exact: true }).waitFor()
        await page.screenshot({ path: path.resolve('../output/topic-submission-desktop.png'), fullPage: true })
        await page.setViewportSize({ width: 390, height: 844 })
        await page.screenshot({ path: path.resolve('../output/topic-submission-mobile.png'), fullPage: true })
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
        const worker = await browser.newPage()
        let action = ''
        const id = '12345678-1234-4234-8234-123456789abc'
        const row = { id, title: submitted.title, owner_email: 'test@example.invalid', status: 'pending', created_at: new Date().toISOString(), request_data: submitted }
        await worker.route('**/api/web-topics**', async route => {
            if (route.request().method() === 'POST') { action = route.request().postDataJSON().action; await route.fulfill({ json: { status: 'rejected' } }); return }
            await route.fulfill({ json: route.request().url().includes(id) ? row : { items: action ? [] : [row] } })
        })
        await worker.goto('http://127.0.0.1:3003')
        await worker.getByRole('button', { name: '웹 토픽 승인' }).click()
        await worker.getByRole('button', { name: '내용 보기' }).click()
        await worker.getByRole('button', { name: '승인 · 대본 작성 시작' }).waitFor()
        await worker.screenshot({ path: path.resolve('../output/topic-submission-worker.png'), fullPage: true })
        await worker.getByLabel('검토 의견 (반려 시 필수)').fill('결말을 보완해주세요')
        await worker.getByRole('button', { name: '반려', exact: true }).click()
        await worker.getByRole('status').filter({ hasText: '토픽을 반려했습니다' }).waitFor()
        assert.equal(action, 'reject')
        assert.deepEqual(errors, [])
        console.log('PASS: real web form, image attachment, submitted payload, pending list, mobile layout, local queue detail and rejection UI (API fixtures; no paid generation)')
    } finally { await browser.close() }
})().catch(e => { console.error(e); process.exitCode = 1 })
