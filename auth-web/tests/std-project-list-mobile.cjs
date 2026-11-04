// Local fixture only: no production data or render jobs are modified.
const { chromium, expect } = require('@playwright/test')
const assert = require('node:assert/strict')
const base = 'http://localhost:3017'
const project = { id:'mobile-fixture', title:'長い日本語のプロジェクトタイトル', category_name:'무협 웹툰', topic_queue_id:3428, updated_at:'2026-11-04T06:00:00Z', title_localization:{title_translations:{ko:'긴 프로젝트 제목'}}, step_status:{isTopicDone:true,isPlanningDone:true,isScriptDone:true,isVideoStepDone:true,videoNotRequired:true,isImageDone:true,isTtsDone:false,isSubtitlesDone:false,isThumbnailDone:false,allDone:false} }
;(async () => {
 const browser = await chromium.launch({channel:'chrome',headless:true})
 try {
  const page = await browser.newPage({viewport:{width:375,height:812},isMobile:true,hasTouch:true})
  await page.addInitScript(() => { localStorage.setItem('std_session_token','fixture'); localStorage.setItem('std_current_nav','topics') })
  await page.route('**/*', async route => {
   const url = new URL(route.request().url())
   if (url.origin !== base) return route.abort()
   if (!url.pathname.startsWith('/api/')) return route.continue()
   let body = {success:true}
   if (url.pathname.endsWith('/me')) body={success:true,user:{id:'fixture',email:'fixture@example.invalid'}}
   if (url.pathname.endsWith('/projects')) body={success:true,projects:[project]}
   if (url.pathname.endsWith('/topics')) body={success:true,topics:[]}
   return route.fulfill({json:body})
  })
  await page.goto(base+'/std?tab=topics',{waitUntil:'domcontentloaded'})
  await page.locator('button[title="주제"]').first().click()
  await expect(page.getByText('프로젝트 목록',{exact:true})).toBeVisible()
  const card = page.locator('article').filter({hasText:project.title})
  await expect(card).toBeVisible()
  await expect(card.getByLabel('영상: 영상 클립 제작 대상이 아닙니다')).toHaveText('×')
  await card.getByRole('checkbox').check()
  await expect(page.getByRole('button',{name:'선택 삭제 (1)'})).toBeEnabled()
  await card.getByRole('checkbox').uncheck()
  const size=await page.locator('article').first().evaluate(el=>({scroll:el.scrollWidth,width:el.clientWidth}))
  assert.ok(size.scroll<=size.width,'mobile card must not overflow horizontally')
  await page.setViewportSize({width:1280,height:800})
  await expect(page.locator('table')).toBeVisible()
  console.log('PASS: mobile project cards, selection, video indicator and desktop table')
 } finally { await browser.close() }
})().catch(error=>{console.error(error);process.exitCode=1})
