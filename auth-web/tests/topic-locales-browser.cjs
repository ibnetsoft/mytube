const { chromium } = require('@playwright/test')
const assert = require('node:assert/strict')
;(async () => {
    const browser = await chromium.launch({ headless: true })
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
        const errors = []; page.on('pageerror', e => errors.push(e.message))
        let searches = [], submitted
        await page.addInitScript(() => { localStorage.setItem('std_session_token', 'test-session'); localStorage.setItem('std_current_nav', 'topic_submissions') })
        await page.route('**/api/std/**', async route => {
            const url = new URL(route.request().url()); let body = { success: true }
            if (url.pathname === '/api/std/me') body = { user: { email: 'test@example.invalid', full_name: 'Tester', preferred_category_ids: [2] } }
            if (url.pathname === '/api/std/topics') body = { topics: [] }
            if (url.pathname === '/api/std/projects') body = { projects: [] }
            if (url.pathname === '/api/std/voices') body = { voices: [] }
            if (url.pathname === '/api/std/topic-submissions') {
                if (route.request().method() === 'POST') { submitted = route.request().postDataJSON(); body = { id: 'test' } }
                else body = { items: [], categories: [{ id: 2, name: '옛날이야기' }] }
            }
            if (url.pathname === '/api/std/topic-youtube') {
                searches.push(Object.fromEntries(url.searchParams))
                const title = url.searchParams.get('language') === 'th' ? 'นิทานครอบครัว' : 'Câu chuyện gia đình'
                body = { source: 'search', keywords: [{ text: title, count: 2 }], videos: [{ id: 'abcdefghijk', title, channel: 'Stories', views: '100', publishedAt: '2026-09-25', thumbnail: 'https://i.ytimg.com/vi/abcdefghijk/mqdefault.jpg', url: 'https://www.youtube.com/watch?v=abcdefghijk', tags: [] }] }
            }
            await route.fulfill({ json: body })
        })
        await page.goto('http://localhost:3000/std?tab=topic_submissions')
        await page.getByRole('heading', { name: '토픽 등록', exact: true }).waitFor()
        await page.getByRole('button', { name: 'ภาษาไทย', exact: true }).click()
        await page.getByRole('heading', { name: 'ลงทะเบียนหัวข้อ', exact: true }).waitFor()
        assert.equal(await page.getByLabel('ภาษาค้นหา', { exact: true }).inputValue(), 'th')
        await page.locator('[name=title]').fill('จดหมายของครอบครัว')
        await page.locator('[name=story]').fill('หญิงสาวพบจดหมายเก่าและกลับไปพบครอบครัว')
        await page.getByLabel('คำค้น YouTube').fill('นิทาน')
        await page.getByRole('button', { name: 'ค้นหา', exact: true }).click()
        await page.getByRole('link', { name: 'นิทานครอบครัว', exact: true }).waitFor()
        assert.equal(searches.at(-1).language, 'th')
        await page.getByRole('button', { name: 'Tiếng Việt', exact: true }).click()
        await page.getByRole('heading', { name: 'Đăng ký chủ đề', exact: true }).waitFor()
        assert.equal(await page.getByLabel('Ngôn ngữ tìm kiếm', { exact: true }).inputValue(), 'vi')
        assert.equal(await page.locator('[name=story]').inputValue(), 'หญิงสาวพบจดหมายเก่าและกลับไปพบครอบครัว')
        await page.getByLabel('Từ khóa tìm YouTube').fill('truyện cổ tích')
        await page.getByRole('button', { name: 'Tìm kiếm', exact: true }).click()
        await page.getByRole('link', { name: 'Câu chuyện gia đình', exact: true }).waitFor()
        assert.equal(searches.at(-1).language, 'vi')
        await page.getByRole('button', { name: 'ภาษาไทย', exact: true }).click()
        await page.getByRole('heading', { name: 'ลงทะเบียนหัวข้อ', exact: true }).waitFor()
        await page.locator('select[name=category]').selectOption('옛날이야기')
        await page.locator('select[name=language]').selectOption('ja')
        await page.locator('[name=character_notes]').fill('สุภาพและกล้าหาญ')
        await page.locator('[name=requirements]').fill('อย่าเปลี่ยนชื่อของตัวละคร')
        await page.setViewportSize({ width: 390, height: 844 })
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
        await page.getByRole('button', { name: 'ลงทะเบียนหัวข้อ · ขออนุมัติ', exact: true }).click()
        await page.getByRole('status').filter({ hasText: 'ลงทะเบียนหัวข้อแล้ว' }).waitFor()
        assert.equal(submitted.language, 'ja')
        assert.equal(submitted.input_language, 'th')
        assert.equal(submitted.category, '옛날이야기')
        assert.equal(submitted.story, 'หญิงสาวพบจดหมายเก่าและกลับไปพบครอบครัว')
        assert.equal(submitted.character_notes, 'สุภาพและกล้าหาญ')
        assert.equal(submitted.requirements, 'อย่าเปลี่ยนชื่อของตัวละคร')
        assert.equal(submitted.ae_scene_delivery, 'gcs')
        assert.deepEqual(errors, [])
        console.log('PASS: Thai/Vietnamese page localization, search language sync/results, preserve multilingual input, mobile and Japanese output submission')
    } finally { await browser.close() }
})().catch(e => { console.error(e); process.exitCode = 1 })
