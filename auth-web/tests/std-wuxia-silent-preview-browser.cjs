const { chromium } = require('@playwright/test')
const assert = require('node:assert/strict')
const base = 'http://127.0.0.1:3029'
const id = 'e9233112-f0d7-4b35-91bf-2f892844eb30'
const scenes = [1, 2, 3].map(n => ({ scene_number: n, image_url: `/fixture/${n}.svg`, duration_seconds: 5 }))
const rows = [{ scene_number: 2, text: '대사입니다.', start_time: 5, end_time: 10, start_num: 5, end_num: 10 }]
const project = { id, title: 'Silent scenes fixture', status: 'in_progress', project_payload: { subtitles: rows, deleted_subtitle_scene_numbers: [1, 3], image_style: 'wuxia_webtoon', structure: { image_style: 'wuxia_webtoon', scenes: scenes.map((scene, index) => ({ ...scene, silent_visual: index !== 1 })) } } }
;(async () => {
 const browser = await chromium.launch({ headless: true, channel: 'chrome' })
 const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })
 const errors = []
 page.on('pageerror', error => errors.push(error.stack))
 await page.addInitScript(() => { localStorage.setItem('std_session_token', 'fixture'); localStorage.setItem('std_current_nav', 'subtitle_vrew') })
 await page.route('**/*', async route => {
  const url = new URL(route.request().url())
  if (url.origin !== base) return route.abort()
  if (url.pathname.startsWith('/fixture/')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>' })
  if (url.pathname.startsWith('/api/')) {
   let body = { success: true }
   if (url.pathname.endsWith('/me')) body = { user: { id: 'fixture', email: 'fixture@example.invalid' } }
   else if (url.pathname.endsWith('/projects')) body = { projects: [project] }
   else if (url.pathname === `/api/std/projects/${id}`) body = { project, scenes, assets: [] }
   else if (url.pathname.endsWith('/speaker-coordinates')) body = { count: 0, completed: 0, confirmed: 0, scenes: [] }
   else if (url.pathname.endsWith('/topics')) body = { topics: [] }
   else if (url.pathname.endsWith('/voices')) body = { voices: [] }
   return route.fulfill({ json: body })
  }
  return route.continue()
 })
 try {
  await page.goto(`${base}/std?tab=subtitle_vrew&projectId=${id}`, { waitUntil: 'domcontentloaded' })
  await page.getByLabel('씬 1 선택', { exact: true }).waitFor({ timeout: 15000 }).catch(async error => { console.log('errors', errors, 'body', (await page.locator('body').innerText()).slice(0, 4000)); throw error })
  await page.getByLabel('씬 1 선택', { exact: true }).check({ timeout: 5000 }).catch(async error => { console.log((await page.locator('body').innerText()).slice(0, 3000)); throw error })
  assert(await page.getByLabel('씬 1 선택', { exact: true }).isChecked())
  await page.getByText('무음 장면').first().click({ timeout: 5000 }).catch(async error => { console.log((await page.locator('body').innerText()).slice(0, 3000)); throw error })
  await page.getByText(/씬 1 미리보기/).waitFor()
  assert((await page.locator('img[alt="Preview"]').getAttribute('src')).includes('/fixture/1.svg'))
  await page.getByRole('button', { name: '씬 미리보기 재생' }).click()
  await page.waitForTimeout(300)
  assert(Number(await page.getByLabel('씬 미리보기 위치').inputValue()) > 0)
  await page.getByLabel('씬 미리보기 위치').fill('2')
  assert.equal(Number(await page.getByLabel('씬 미리보기 위치').inputValue()), 2)
  await page.getByText('대사입니다.', { exact: true }).first().click()
  assert.equal(await page.getByLabel('씬 미리보기 위치').count(), 0)
  assert.deepEqual(errors, [])
  console.log('silent scene selection, preview, playback and seek passed')
 } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
