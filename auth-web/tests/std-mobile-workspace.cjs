// Mobile layout smoke test with local API fixtures only.
const { chromium } = require('@playwright/test')
const assert = require('node:assert/strict')
const width=Number(process.env.STD_MOBILE_WIDTH || 375)
const base = 'http://localhost:3017', id = '00000000-0000-4000-8000-000000000100'
const scenes = Array.from({length:3},(_,i)=>({scene_number:i+1,scene_text:'日本語のナレーションです。',image_url:'/fixture.svg',start_seconds:i*5,end_seconds:(i+1)*5,duration_seconds:5}))
const subtitles = scenes.map((scene,i)=>({id:`s${i}`,scene_number:i+1,text:scene.scene_text,start_num:i*5,end_num:(i+1)*5,start_time:i*5,end_time:(i+1)*5,translation_manual:true}))
const project={id,title:'모바일 화면 확인 프로젝트',status:'in_progress',language:'ja',project_payload:{script:'日本語のナレーションです。',structure:{required_video_scene_count:0,scenes},scenes,subtitles,render_settings:{}},progress_payload:{}}
const topic={id:3428,topic:'日本語の長いタイトル テスト',generated_title:'日本語の長いタイトル テスト',category_name:'무협 웹툰',language:'ja',assigned_duration_minutes:10,scene_count:26,video_not_required:true,pregenerated_structure:{scenes}}
;(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true})
 try {
  const page=await browser.newPage({viewport:{width,height:812},isMobile:true,hasTouch:true})
  const errors=[];page.on('pageerror',error=>errors.push(error.message))
  await page.addInitScript(()=>{localStorage.setItem('std_session_token','fixture')})
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url()); if(u.origin!==base)return route.abort()
   if(u.pathname==='/fixture.svg')return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="green"/></svg>'})
   if(!u.pathname.startsWith('/api/'))return route.continue()
   let body={success:true};if(u.pathname.endsWith('/me'))body={success:true,user:{id:'fixture',email:'fixture@example.invalid'}}
   if(u.pathname.endsWith('/projects'))body={success:true,projects:[project]}
   if(u.pathname===`/api/std/projects/${id}`)body={success:true,project,scenes,assets:[]}
   if(u.pathname.endsWith('/topics'))body={success:true,topics:[topic]}
   if(u.pathname.endsWith('/topic-submissions'))body={success:true,items:[],categories:[]}
   if(u.pathname.endsWith('/voices'))body={success:true,voices:[]}
   if(u.pathname.endsWith('/speaker-coordinates'))body={success:true,scenes:[],state:'complete',count:0,results:[]}
   return route.fulfill({json:body})
  })
  for(const tab of ['topics','image_gen','subtitle_vrew','thumbnail','template','settings','topic_submissions']){
   await page.goto(`${base}/std?tab=${tab}&projectId=${id}`,{waitUntil:'domcontentloaded'})
   await page.waitForSelector('main',{timeout:30000})
   await page.waitForTimeout(1500)
   const result=await page.evaluate(()=>{
    const main=document.querySelector('main'); const rect=main?.getBoundingClientRect()
    return {width:innerWidth,mainWidth:main?.clientWidth,mainScroll:main?.scrollWidth,overflow:[...main?.querySelectorAll('*')||[]].map(e=>({el:e.tagName,cls:String(e.className).slice(0,120),rect:e.getBoundingClientRect(),sw:e.scrollWidth,cw:e.clientWidth})).filter(x=>x.rect.width>0&&x.rect.right>innerWidth+8&&x.rect.left<innerWidth).slice(0,8).map(({el,cls,rect,sw,cw})=>({el,cls,left:Math.round(rect.left),right:Math.round(rect.right),sw,cw}))}
   })
   console.log(tab,JSON.stringify(result))
   if(process.env.STD_MOBILE_SCREENSHOTS)await page.screenshot({path:`${process.env.STD_MOBILE_SCREENSHOTS}/air-mobile-${tab}-${width}.png`})
   assert.ok(result.mainWidth>0,`${tab}: workspace visible`)
   assert.ok(result.mainScroll<=result.mainWidth+1,`${tab}: main content fits mobile viewport`)
   if(tab==='topics') {
    await page.getByText(topic.generated_title,{exact:true}).first().click()
    const dialog=page.getByRole('dialog',{name:'주제 상세'})
    assert.ok(await dialog.isVisible(),'topic details open')
    const box=await dialog.boundingBox()
    assert.ok(box.height<=812*.9+1 && box.width<=width,'topic details fit and scroll within viewport')
    await dialog.getByRole('button',{name:'취소'}).click()
   }
   if(tab==='subtitle_vrew') {
    const source=page.locator('[data-subtitle-index="0"]').getByTitle(scenes[0].scene_text).first()
    assert.equal(await source.evaluate(el=>getComputedStyle(el).whiteSpace),'normal','subtitle source wraps on mobile')
    const thumb=page.locator('.std-subtitle-body').locator('[class*="w-28"]').first()
    assert.ok((await thumb.boundingBox()).width<150,'subtitle scene thumbnail stays compact')
    await page.getByTitle('스타일 패널 펼치기').click()
    assert.equal(await page.getByTitle('스타일 패널 숨기기').getAttribute('aria-expanded'),'true','subtitle style controls open')
   }
   if(tab==='template') {
    const text=page.locator('[data-template-canvas] > div.whitespace-nowrap').first()
    assert.ok(parseFloat(await text.evaluate(el=>getComputedStyle(el).fontSize))<30,'template text scales down on mobile')
   }
   if(tab==='settings') {
    const support=page.getByRole('button',{name:'💬 문의하기'})
    const box=await support.boundingBox()
    assert.ok(box && box.x>=0 && box.x+box.width<=width,'settings tabs remain visible without horizontal scrolling')
   }
  }
  assert.deepEqual(errors,[],'mobile screens have no uncaught runtime errors')
 } finally {await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1})
