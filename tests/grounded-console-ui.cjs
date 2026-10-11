// Browser routing uses a synthetic reference library; no real source/job writes.
const { chromium } = require('../auth-web/node_modules/@playwright/test');
const fs = require('fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const refs=[];let jobPosts=0;
  await page.route('**/api/references*',async route=>{
    if(route.request().method()==='POST'){
      const row=route.request().postDataJSON();row.id='a'.repeat(32);row.characters=row.text.length;refs.push(row);
      return route.fulfill({json:{id:row.id}});
    }
    return route.fulfill({json:{items:refs}});
  });
  await page.route('**/api/jobs',async route=>{jobPosts++;return route.fulfill({status:409,json:{detail:'test only'}});});
  await page.goto('http://127.0.0.1:3003');
  await page.getByRole('button',{name:'▤   기독교 설교 · 자료실',exact:true}).click();
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
  const form=page.locator('#grounded-form');
  if(await form.locator('[name=duration_minutes]').inputValue()!=='135')throw Error('Long sermon default missing');
  await form.locator('[name=grounded_type]').selectOption('education');
  if(await form.locator('[name=duration_minutes]').getAttribute('max')!=='60')throw Error('Education limit changed');
  await form.locator('[name=grounded_type]').selectOption('sermon');
  if(await form.locator('[name=duration_minutes]').getAttribute('max')!=='360')throw Error('Long sermon limit missing');
  await form.locator('[name=duration_minutes]').fill('135');
  await form.locator('[name=title]').fill('인공 설교 테스트');
  await form.locator('[name=passage]').fill('테스트 1:1');
  await form.locator('[name=perspective]').fill('인공 테스트');
  await form.locator('button[type=submit]').click();
  await page.waitForTimeout(150);
  if(jobPosts!==1)throw Error('Long sermon submission not wired');
  fs.mkdirSync('output/codex-local-console/qa',{recursive:true});
  await page.screenshot({path:'output/codex-local-console/qa/grounded.png',fullPage:true});
  if(errors.length)throw new Error(errors.join('\n'));
  console.log('Grounded UI passed: registration/selection (mocked), no real writes or paid generation.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
