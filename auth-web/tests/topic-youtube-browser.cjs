const { chromium } = require('@playwright/test')
const assert = require('node:assert/strict')
const path = require('node:path')
;(async () => {
    const browser = await chromium.launch({ headless: true })
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
        const errors = []; page.on('pageerror', error => errors.push(error.message))
        let searches = [], submissions = [], mode = 'ok'
        await page.addInitScript(() => { localStorage.setItem('std_session_token', 'test-session'); localStorage.setItem('std_current_nav', 'topic_submissions') })
        await page.route('**/api/std/**', async route => {
            const url = new URL(route.request().url()); let body = { success: true }, status = 200
            if (url.pathname === '/api/std/me') body = { user: { email: 'test@example.invalid', full_name: '테스트 사용자', preferred_category_ids: [2] } }
            if (url.pathname === '/api/std/topics') body = { topics: [] }
            if (url.pathname === '/api/std/projects') body = { projects: [] }
            if (url.pathname === '/api/std/voices') body = { voices: [] }
            if (url.pathname === '/api/std/topic-submissions') {
                if (route.request().method() === 'POST') { submissions.push(route.request().postDataJSON()); body = { id: 'test' } }
                else body = { items: [], categories: [{ id: 2, name: '옛날이야기' }] }
            }
            if (url.pathname === '/api/std/topic-youtube') {
                searches.push(Object.fromEntries(url.searchParams))
                body = { source: url.searchParams.get('q') ? 'search' : 'popular', keywords: [{ text: '가족', count: 3 }, { text: '약속', count: 1 }], videos: [{ id: 'abcdefghijk', title: '가족의 약속 · 참고 영상', channel: '이야기 채널', publishedAt: '2026-09-25T12:00:00Z', views: '12345', thumbnail: 'https://i.ytimg.com/vi/abcdefghijk/mqdefault.jpg', url: 'https://www.youtube.com/watch?v=abcdefghijk', tags: ['가족'] }] }
                if (mode === 'empty') body = { videos: [], keywords: [], source: 'search' }
                if (mode === 'error') { body = { error: 'YouTube API 사용량 또는 키 설정을 확인해야 합니다.' }; status = 503 }
            }
            await route.fulfill({ json: body, status })
        })
        await page.goto('http://localhost:3000/std?tab=topic_submissions')
        await page.getByRole('heading', { name: 'YouTube 참고 영상 찾기' }).waitFor()
        assert.equal(searches.length, 0)
        await page.locator('[name=title]').fill('직접 작성한 제목')
        await page.locator('[name=story]').fill('직접 작성한 줄거리')
        await page.getByRole('button', { name: '인기 영상·키워드 불러오기' }).click()
        await page.getByRole('button', { name: '참고 영상으로 선택', exact: true }).waitFor()
        assert.equal(searches[0].q, '')
        assert.equal(submissions.length, 0)
        await page.getByRole('button', { name: '가족', exact: true }).click()
        await page.getByText('“가족” 검색 결과 · 1개', { exact: true }).waitFor()
        assert.equal(searches[1].q, '가족')
        await page.getByRole('button', { name: '참고 영상으로 선택', exact: true }).click()
        assert.equal(await page.locator('[name=youtube_url]').inputValue(), 'https://www.youtube.com/watch?v=abcdefghijk')
        assert.equal(await page.locator('[name=title]').inputValue(), '직접 작성한 제목')
        assert.equal(await page.locator('[name=story]').inputValue(), '직접 작성한 줄거리')
        await page.getByLabel('검색 언어', { exact: true }).selectOption('ja')
        await page.getByLabel('검색 정렬', { exact: true }).selectOption('viewCount')
        await page.getByLabel('검색 기간', { exact: true }).selectOption('week')
        await page.getByLabel('YouTube 검색 키워드').fill('日本昔話')
        await page.getByLabel('YouTube 검색 키워드').press('Enter')
        await page.getByText('“日本昔話” 검색 결과 · 1개', { exact: true }).waitFor()
        assert.deepEqual(searches.at(-1), { q: '日本昔話', language: 'ja', order: 'viewCount', period: 'week' })
        assert.equal(submissions.length, 0)
        await page.locator('[name=title]').fill('')
        await page.getByRole('button', { name: '✓ 참고 영상 선택됨', exact: true }).click()
        assert.equal(await page.locator('[name=title]').inputValue(), '가족의 약속 · 참고 영상')
        await page.getByRole('heading', { name: 'YouTube 참고 영상 찾기' }).scrollIntoViewIfNeeded()
        await page.screenshot({ path: path.resolve('../output/topic-youtube-desktop.png') })
        await page.setViewportSize({ width: 390, height: 844 })
        await page.screenshot({ path: path.resolve('../output/topic-youtube-mobile.png'), fullPage: true })
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false)
        mode = 'empty'
        await page.getByRole('button', { name: '검색', exact: true }).click()
        await page.getByText(/다른 검색어나 기간으로 검색/).waitFor()
        mode = 'error'
        await page.getByRole('button', { name: '검색', exact: true }).click()
        await page.getByRole('alert').filter({ hasText: 'YouTube API 사용량' }).waitFor()
        assert.deepEqual(errors, [])
        await page.locator('select[name=category]').selectOption('옛날이야기')
        await page.getByRole('button', { name: '토픽 등록 · 승인 요청' }).click()
        await page.getByRole('status').filter({ hasText: '토픽을 등록했습니다' }).waitFor()
        assert.equal(submissions.length, 1)
        assert.equal(submissions[0].youtube_url, 'https://www.youtube.com/watch?v=abcdefghijk')
        assert.equal(submissions[0].ae_scene_delivery, 'gcs')
        console.log('PASS: discovery, cloud click, search filters/Enter, URL selection, preserve edits, no accidental submission, mobile, errors, and final topic payload')
    } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
