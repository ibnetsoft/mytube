const assert = require('node:assert/strict');
const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:3004/');
    await page.waitForFunction(() => document.querySelector('#scope').textContent.includes('조회'));
    assert.match(await page.locator('#connection').textContent(), /로컬 연결됨/);
    await page.screenshot({ path: '../output/local-media/dashboard.png', fullPage: true });
    await page.route('**/jobs', route => route.fulfill({ json: { jobs: [
      { id:'a', title:'<script>bad</script>', kind:'ae_mouth_job', state:'review_pending', group:'review',total:10,analyzed:10,done:2 },
      { id:'b', title:'렌더 테스트', kind:'render', state:'rendering', group:'working',progress:42 },
    ], updated_at:new Date().toISOString(), error:null } }));
    await page.locator('#refresh').click();
    await page.waitForFunction(() => document.querySelector('#scope').textContent.includes('조회 2건'));
    assert.equal(await page.locator('article script').count(), 0);
    assert.match(await page.locator('#jobs').textContent(), /실제 렌더 진행률 42%/);
    await page.getByRole('button', { name:'검수 필요', exact:true }).click();
    assert.equal(await page.locator('article').count(), 1);
    await page.locator('#search').fill('없음');
    assert.match(await page.locator('#jobs').textContent(), /해당하는 작업이 없습니다/);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.route('**/jobs', route => route.fulfill({ json: {jobs:[],updated_at:null,error:'TimeoutError'} }));
    await page.locator('#refresh').click();
    await page.waitForFunction(() => document.querySelector('#error').textContent.includes('TimeoutError'));
    assert.deepEqual(errors, []);
    console.log('Dashboard live data, rendering, filters, safe text, mobile layout and connection errors passed');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
