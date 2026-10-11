const {chromium}=require('@playwright/test'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage();page.setDefaultTimeout(12000);let submitted;
 await page.addInitScript(()=>{localStorage.setItem('std_session_token','fixture');localStorage.setItem('std_current_nav','topic_submissions')});
 await page.route('**/api/std/**',async r=>{const pathname=new URL(r.request().url()).pathname;let data={projects:[],topics:[],voices:[]};
 if(pathname.endsWith('/me'))data={user:{email:'fixture@test.invalid',preferred_category_ids:[15]}};
 if(pathname.endsWith('/topic-submissions')){if(r.request().method()==='POST'){submitted=r.request().postDataJSON();data={id:'fixture'}}else data={items:[],categories:[{id:2,name:'옛날이야기'},{id:15,name:'일본사건'}]};}
 await r.fulfill({json:data})});
 await page.goto('http://localhost:3000/std?tab=topic_submissions',{waitUntil:'domcontentloaded'});
 await page.locator('select[name=category]').selectOption('일본사건');
 assert.equal(await page.locator('[name=duration_minutes]').inputValue(),'15');
 assert.equal(await page.locator('[name=language]').inputValue(),'ja');
 assert.equal(await page.locator('input[value=jp_domestic_watercolor]').isChecked(),true);
 await page.locator('[name=title]').fill('현관에 남겨진 봉투');await page.locator('[name=story]').fill('배우자의 거짓말을 알게 된 주인공이 정당한 증거를 보존하고 새로운 생활을 시작한다.');
 await page.getByRole('button',{name:'토픽 등록 · 승인 요청'}).click();await page.getByRole('status').filter({hasText:'토픽을 등록했습니다'}).waitFor();
 assert.equal(submitted.category,'일본사건');assert.equal(submitted.image_style,'jp_domestic_watercolor');assert.equal(submitted.language,'ja');
 const worker=await browser.newPage();await worker.route('**/api/**',r=>r.fulfill({json:r.request().url().includes('/categories')?{items:[{id:15,name:'일본사건'}]}:{jobs:[],items:[],storage:{connected:true},cloud_summary:{}}}));
 await worker.goto('http://127.0.0.1:3003',{waitUntil:'domcontentloaded'});await worker.locator('button[data-view=new]').first().click();
 await worker.locator('#new-script-style').selectOption('japanese_domestic_drama');
 assert.equal(await worker.locator('#category').inputValue(),'일본사건');assert.equal(await worker.locator('#new-style').inputValue(),'jp_domestic_watercolor');assert.equal(await worker.locator('#new-form [name=required_video_scene_count]').inputValue(),'0');assert.equal(await worker.locator('#new-form [name=generate_bgm_prompt]').isChecked(),true);
 console.log('PASS: Japanese domestic category defaults, web request and local worker style settings (API fixtures; no paid generation)');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
