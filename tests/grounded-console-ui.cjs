// Browser routing uses a synthetic reference library; no real source/job writes.
const { chromium } = require('../auth-web/node_modules/@playwright/test');
const fs = require('fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const refs=[];let jobPosts=0;
  await page.route('**/api/references',async route=>{
    if(route.request().method()==='POST'){
      const row=route.request().postDataJSON();row.id='a'.repeat(32);row.characters=row.text.length;refs.push(row);
      return route.fulfill({json:{id:row.id}});
    }
    return route.fulfill({json:{items:refs}});
  });
  await page.route('**/api/jobs',async route=>{jobPosts++;return route.fulfill({status:409,json:{detail:'test only'}});});
  await page.goto('http://127.0.0.1:3003');
  await page.getByRole('button',{name:'▤   자료 기반 생성',exact:true}).click();
  await page.locator('#reference-form').waitFor({state:'visible'});
  await page.locator('#reference-form [name=title]').fill('합성 테스트 원문');
  await page.locator('#reference-form [name=locator]').fill('테스트 1:1');
  await page.locator('#reference-form [name=translation]').fill('실제 성경 아님');
  await page.locator('#source-text').fill('그는 집으로 돌아왔습니다.');
  await page.locator('#reference-form [name=permission_notes]').fill('테스트용 원문');
  await page.locator('#reference-form button[type=submit]').click();
  await page.locator('#reference-list input').waitFor();
  await page.locator('#reference-list input').check();
  if(refs.length!==1)throw new Error('Registration not wired');
  if(jobPosts)throw new Error('Unexpected generation');
  fs.mkdirSync('output/codex-local-console/qa',{recursive:true});
  await page.screenshot({path:'output/codex-local-console/qa/grounded.png',fullPage:true});
  if(errors.length)throw new Error(errors.join('\n'));
  console.log('Grounded UI passed: registration/selection (mocked), no real writes or paid generation.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
