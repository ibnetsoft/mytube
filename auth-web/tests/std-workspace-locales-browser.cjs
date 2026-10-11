const {chromium}=require('@playwright/test');const fs=require('node:fs');const assert=require('node:assert/strict');const load=require('./load-ts-module.cjs');const {I18N_DICTIONARY}=load('auth-web/lib/i18n.ts');const {stdUiText}=load('auth-web/lib/stdUiText.ts');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{localStorage.setItem('std_session_token','test-session');localStorage.setItem('std_current_nav','thumbnail');});
 await page.route('**/api/std/**',async route=>{const p=new URL(route.request().url()).pathname;let body={success:true};if(p==='/api/std/me')body={user:{email:'test@example.invalid',full_name:'Original Name',preferred_category_ids:[]}};if(p==='/api/std/projects')body={projects:[]};if(p==='/api/std/topics')body={topics:[]};if(p==='/api/std/voices')body={voices:[]};if(p==='/api/std/topic-submissions')body={items:[],categories:[]};await route.fulfill({json:body});});
 await page.goto('http://localhost:3000/std?tab=thumbnail');
 let initialized=false;
 for(const [locale,button] of [['en','English'],['vi','Tiếng Việt'],['th','ภาษาไทย'],['ko','한국어']]){
  await page.getByRole('button',{name:button,exact:true}).click();
  await page.getByRole('button',{name:I18N_DICTIONARY[locale].nav_thumbnail,exact:true}).first().click();
  await page.getByText(stdUiText(locale,'영상 제목 및 기획 의도'),{exact:true}).waitFor();
  await page.getByText(stdUiText(locale,'글자 없는 배경 이미지를 생성하거나 업로드해 주세요.'),{exact:true}).waitFor();
  const title=page.getByPlaceholder(stdUiText(locale,'영상의 주요 내용이나 기획 의도를 입력하세요.'));if(initialized)assert.equal(await title.inputValue(),'日本語のユーザー入力');await title.fill('日本語のユーザー入力');
  await page.getByRole('button',{name:I18N_DICTIONARY[locale].nav_template,exact:true}).first().click();
  await page.getByText(stdUiText(locale,'💾 템플릿 프리셋 관리'),{exact:true}).waitFor();
  const preset=page.getByPlaceholder(stdUiText(locale,'새 프리셋 이름'));if(initialized)assert.equal(await preset.inputValue(),'Original 日本語 preset');await preset.fill('Original 日本語 preset');
  await page.getByRole('button',{name:I18N_DICTIONARY[locale].nav_settings,exact:true}).first().click();
  await page.getByText(stdUiText(locale,'■■ 기본 설정'),{exact:true}).click();
  await page.getByText(stdUiText(locale,'🔑 내 추천 코드 및 초대 링크'),{exact:true}).waitFor();
  if(locale==='vi'){fs.mkdirSync('output/ui-locales',{recursive:true});await page.screenshot({path:'output/ui-locales/settings-vi.png'});}
  await page.getByText(stdUiText(locale,'💬 문의하기'),{exact:true}).click();
  const select=page.locator('select').filter({has:page.locator('option[value="시스템 문의"]')});
  await select.selectOption('정산 문의');assert.equal(await select.inputValue(),'정산 문의');
  await page.getByRole('button',{name:I18N_DICTIONARY[locale].nav_template,exact:true}).first().click();assert.equal(await preset.inputValue(),'Original 日本語 preset');
  await page.getByRole('button',{name:I18N_DICTIONARY[locale].nav_thumbnail,exact:true}).first().click();assert.equal(await title.inputValue(),'日本語のユーザー入力');initialized=true;
 }
 await page.getByRole('button',{name:'ภาษาไทย',exact:true}).click();await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);console.log('PASS: KO/EN/VI/TH thumbnail, template, settings, preserved input/option values and mobile layout');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
