const { chromium } = require('@playwright/test');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage();
    const brief = {title:'Thai topic',story:'Original story',character_notes:'Characters',requirements:'Requirements',transcript:'Reference',youtube_url:'https://www.youtube.com/watch?v=test',category:'옛날이야기',duration_minutes:5,input_language:'th',language:'ko',setting_country:'Thailand',era_region:'Modern village',image_style:'realistic',production_mode:'standard',ae_scene_delivery:'gcs',character_images:[{name:'Mali.png',data:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jV9sAAAAASUVORK5CYII='}]};
    const row = {id:'fixture',title:brief.title,owner_email:'review@example.com',status:'pending',created_at:'2026-10-01T00:00:00Z',request_data:brief};
    await page.route('**/api/web-topics**', async route => {
      const url = route.request().url();
      assert(!url.endsWith('/review'), 'Must never approve during verification');
      const body = url.includes('korean-review') ? {status:'completed',translation:{title:'한국어 제목',story:'한국어 이야기',character_notes:'인물 설명',requirements:'필수 지침',transcript:'참고 자료',setting_country:'태국',era_region:'현대 마을'}} : url.includes('?') ? {items:[row]} : row;
      await route.fulfill({json:body});
    });
    await page.goto('http://127.0.0.1:3003/');
    await page.getByRole('button',{name:'웹 토픽 승인',exact:false}).click();
    await page.getByRole('button',{name:'내용 보기',exact:true}).click();
    await page.getByText('한국어 제목',{exact:true}).waitFor();
    for(const [label,value] of [['카테고리','옛날이야기'],['이미지 스타일','실사'],['입력 언어','태국어'],['대본 언어','한국어'],['배경 국가','태국'],['시대·지역','현대 마을'],['분량','5분'],['제작 모드','기존 영상'],['AE 씬 영상 전달 방식','GCS 업로드']]) {
      assert.equal(await page.locator('.topic-review-settings > div').filter({has:page.locator('dt',{hasText:label})}).locator('dd').textContent(),value);
    }
    assert.equal(await page.locator('img[alt="Mali.png"]').count(),2);
    await page.getByText('원본 크기로 보기',{exact:true}).click();
    assert(await page.getByRole('img',{name:'Mali.png',exact:true}).last().isVisible());
    assert(await page.getByRole('button',{name:'승인 · 대본 작성 시작',exact:true}).isVisible());
    brief.character_images=[];brief.transcript='';brief.youtube_url='';
    await page.getByRole('button',{name:'내용 보기',exact:true}).click();
    await page.getByText('첨부 없음',{exact:true}).waitFor();
    assert(await page.getByText('미입력',{exact:true}).count() > 0);
    console.log('Topic review: labeled settings, Korean translation, attachments/full size, empty fields and approval controls passed.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
