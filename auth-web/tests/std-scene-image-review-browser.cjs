const { chromium } = require('@playwright/test')
const assert = require('node:assert/strict')
const base = 'http://127.0.0.1:3029'
const id = 'e9233112-f0d7-4b35-91bf-2f892844eb30'
const scenes = [1, 2, 3].map(n => ({ scene_number:n, image_url:`/fixture/${n}.svg`, duration_seconds:5 }))
const rows = [{ scene_number:2, text:'대사입니다.', start_time:5, end_time:10, start_num:5, end_num:10 }]
const project = { id, title:'씬 교체 시험', status:'in_progress', project_payload:{ subtitles:rows,
 deleted_subtitle_scene_numbers:[1,3], image_style:'wuxia_webtoon', structure:{ image_style:'wuxia_webtoon',
 scenes:scenes.map((scene,index)=>({...scene,silent_visual:index!==1})) } } }
;(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'})
 const page=await browser.newPage({viewport:{width:1500,height:1000}});const errors=[];let sent=0;let reviews=[]
 page.on('pageerror',error=>errors.push(error.message))
 await page.addInitScript(()=>{localStorage.setItem('std_session_token','fixture');localStorage.setItem('std_current_nav','subtitle_vrew')})
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());if(url.origin!==base)return route.abort()
  if(url.pathname.startsWith('/fixture/'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'})
  if(!url.pathname.startsWith('/api/'))return route.continue()
  let body={success:true}
  if(url.pathname.endsWith('/me'))body={user:{id:'fixture',email:'fixture@example.invalid'}}
  else if(url.pathname.endsWith('/projects'))body={projects:[project]}
  else if(url.pathname===`/api/std/projects/${id}`)body={project,scenes,assets:[]}
  else if(url.pathname.endsWith('/scene-image-review')){
   if(route.request().method()==='POST'){sent++;reviews=[{id:'review-1',scene_number:1,status:'completed'}];body={success:true,review:{id:'review-1',status:'queued'}}}
   else body={success:true,reviews}
  }
  else if(url.pathname.endsWith('/speaker-coordinates'))body={count:0,completed:0,confirmed:0,scenes:[]}
  else if(url.pathname.endsWith('/topics'))body={topics:[]}
  else if(url.pathname.endsWith('/voices'))body={voices:[]}
  return route.fulfill({json:body})
 })
 try{
  await page.goto(`${base}/std?tab=subtitle_vrew&projectId=${id}`,{waitUntil:'domcontentloaded'})
  await page.getByLabel('씬 1 이미지 교체',{exact:true}).waitFor({state:'attached',timeout:20000})
  assert.equal(await page.getByLabel('씬 2 이미지 교체',{exact:true}).count(),1)
  await page.getByLabel('씬 1 이미지 교체',{exact:true}).setInputFiles({name:'candidate.png',mimeType:'image/png',buffer:Buffer.from('test')})
  await page.getByText('검수 완료 · 입모양·효과 재검토',{exact:false}).waitFor({timeout:15000})
  assert.equal(sent,1);assert.deepEqual(errors,[])
  console.log('silent and spoken scene upload controls and review status passed')
 } finally { await browser.close() }
})().catch(error=>{console.error(error);process.exitCode=1})
