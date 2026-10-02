const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();const failures=[];page.on('pageerror',e=>failures.push(e.message));
  await page.goto('http://127.0.0.1:3003/');
  await page.getByRole('button',{name:'대본 지침 개선',exact:false}).click();
  await page.getByRole('heading',{name:'적용 결과 · 최근 대본 검수'}).waitFor();
  assert(await page.locator('#view-guidelines').isVisible());
  let row=null,posts=0;
  await page.route('**/api/script-guidelines**',async route=>{
   const request=route.request();const data=request.postDataJSON();
   if(request.method()==='GET'){await route.fulfill({json:{items:row?[row]:[],outcomes:[]}});return;}
   assert(!request.url().endsWith('/notion-sync'),'No external sync during testing');posts++;
   if(request.url().endsWith('/review'))row.status=data.action==='approve'?'approved':'retired';
   else row={...data,id:'fixture',version:1,status:'pending',review_note:''};
   await route.fulfill({json:row});
  });
  const form=page.locator('#view-guidelines form');
  await form.getByLabel('개선안 제목').fill('시대 고증');
  await form.getByLabel('발견한 문제·수정/반려 사유').fill('시대에 맞지 않는 도구');
  await form.getByLabel('다음 대본 작성·검수에 적용할 개선 지침').fill('시대에 맞는 도구만 묘사');
  await form.getByRole('button',{name:'개선안 저장 · 승인 대기'}).click();
  await page.getByRole('heading',{name:'v1 · 시대 고증 · 승인 대기'}).waitFor();
  assert(await page.getByRole('button',{name:'Notion 열람용 복사 (선택)'}).isDisabled());
  await page.getByRole('button',{name:'승인 · 다음 작업부터 적용'}).click();
  await page.getByRole('heading',{name:'v1 · 시대 고증 · 적용 중'}).waitFor();
  assert(await page.getByRole('button',{name:'Notion 열람용 복사 (선택)'}).isEnabled());
  await page.locator('#view-guidelines article article textarea').fill('더 구체적인 지침으로 교체');
  await page.getByRole('button',{name:'비활성화',exact:true}).click();
  await page.getByRole('heading',{name:'v1 · 시대 고증 · 비활성화'}).waitFor();
  assert.equal(posts,3);assert.deepEqual(failures,[]);
  console.log('PASS: live guideline/outcome view, feedback proposal, approval, retirement, optional Notion gating; no generation or external writes.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
