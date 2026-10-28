const {chromium}=require('../auth-web/node_modules/@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const page=await browser.newPage(); const errors=[];
  page.on('pageerror', e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:3003');
  await page.locator('nav [data-view="new"]').click();
  await page.locator('#new-form button').filter({hasText:'현대 일본 · 비 오는 골목 수채 애니 설정'}).click();
  await page.waitForFunction(()=>document.querySelector('#new-style').value==='비 오는 골목 수채 애니');
  const read=prefix=>page.locator('#'+prefix+'-form').evaluate(f=>Object.fromEntries(['language','setting_country','era_region','image_style','notes','category','custom_category'].filter(k=>f.elements[k]).map(k=>[k,f.elements[k].value])));
  const fresh=await read('new'); assert.equal(fresh.language,'ja');assert.equal(fresh.setting_country,'일본');assert.equal(fresh.custom_category,'현대 일본 휴먼드라마');assert.equal(fresh.category,'');assert.ok(fresh.notes.includes('현대 일본'));
  await page.locator('nav [data-view="grounded"]').click();
  await page.locator('#topic-form button').filter({hasText:'현대 일본 · 비 오는 골목 수채 애니 설정'}).click();
  await page.waitForFunction(()=>document.querySelector('#topic-style').value==='비 오는 골목 수채 애니');
  const topic=await read('topic');assert.equal(topic.language,'ja');assert.equal(topic.category,'현대 일본 휴먼드라마');assert.equal(topic.image_style,fresh.image_style);
  assert.deepEqual(errors,[]);
  console.log('PASS: both live forms apply Japanese modern drama and watercolor preset; no generation invoked');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
