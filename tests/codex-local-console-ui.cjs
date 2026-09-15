// Read-only live smoke: no generation/approval/DB mutations.
const { chromium } = require('../auth-web/node_modules/@playwright/test');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1480,height:1050}});
    const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:3003');
    await page.getByRole('heading',{name:'CLI 설치 확인',exact:true}).waitFor();
    await page.getByRole('button',{name:'리페어 대본 목록 →',exact:true}).click();
    await page.locator('#catalog tr').first().waitFor({timeout:60000});
    const count = await page.locator('#catalog-count').innerText();
    if (!count.includes('전체')) throw new Error('Catalog did not load: '+count);
    console.log('Topics:',count);
    await page.locator('#search').fill('3197');
    await page.locator('#search-button').click();
    await page.waitForFunction(()=>document.querySelector('#catalog-count').textContent==='전체 1건',{},{timeout:60000});
    await page.getByRole('button',{name:'대본 읽기',exact:true}).click();
    await page.locator('#source-panel').waitFor({state:'visible',timeout:60000});
    console.log('3197 source loaded; characters:',(await page.locator('#source-script').innerText()).length);
    await page.locator('#search').fill('');
    await page.locator('#kind').selectOption('project');
    await page.waitForFunction(()=>document.querySelector('#catalog-count').textContent.startsWith('전체 '),{},{timeout:60000});
    console.log('Projects:',await page.locator('#catalog-count').innerText());
    fs.mkdirSync('output/codex-local-console/qa',{recursive:true});
    await page.screenshot({path:'output/codex-local-console/qa/repair.png',fullPage:true});
    await page.getByRole('button',{name:'＋   신규 생성'}).count();
    await page.locator('nav [data-view="new"]').click();
    await page.locator('#new-form').waitFor({state:'visible'});
    console.log('Categories:',await page.locator('#category option').count());
    await page.locator('[data-doc="repair"]').click();
    await page.locator('#document').waitFor({state:'visible'});
    if (!(await page.locator('#document').innerText()).includes('필수 원칙')) throw new Error('Repair manual missing');
    if(errors.length)throw new Error(errors.join('\n'));
    console.log('UI smoke passed; no generation or approval invoked.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
