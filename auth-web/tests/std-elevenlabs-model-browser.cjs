const assert = require('node:assert/strict');
const {chromium} = require('@playwright/test');
const base = process.env.STD_VOICE_TEST_URL || 'http://127.0.0.1:3016';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname));
const id = 'e9233112-f0d7-4b35-91bf-2f892844eb30';
const voiceId = 'FGY2WhTYpPnrIDTdsKH5';
const project = {id,title:'ElevenLabs model fixture',status:'in_progress',language:'ko',project_payload:{script:'비가 그쳤습니다.',voice_id:voiceId,subtitles:[{id:'s1',text:'비가 그쳤습니다.',scene_number:1,start_time:0,end_time:4,voice_id:voiceId}]},progress_payload:{}};
(async()=>{
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1500,height:1000}});
    const errors = [], requests = [];
    page.on('pageerror', e=>errors.push(e.message));
    page.on('console', msg=>{if(msg.type()==='error') console.log('browser console:',msg.text())});
    page.on('dialog', d=>d.dismiss());
    await page.addInitScript(()=>localStorage.setItem('std_session_token','fixture'));
    await page.route('**/api/**',async route=>{
      const url = new URL(route.request().url()); let body = {success:true};
      if(url.pathname.endsWith('/me'))body={user:{id:'fixture',email:'fixture@example.invalid',full_name:'fixture'}};
      if(url.pathname.endsWith('/projects'))body={projects:[project]};
      if(url.pathname===`/api/std/projects/${id}`)body={project,scenes:[{scene_number:1,scene_text:'비가 그쳤습니다.',start_seconds:0,end_seconds:4,duration_seconds:4}],assets:[]};
      if(url.pathname.endsWith('/topics'))body={topics:[]};
      if(url.pathname.endsWith('/voices'))body={voices:[{id:voiceId,name:'Laura'}]};
      if(url.pathname.endsWith('/speaker-coordinates'))body={count:0,completed:0,confirmed:0,scenes:[]};
      if(url.pathname.endsWith('/tts/generate')){
        requests.push(route.request().postDataJSON());
        return route.fulfill({status:422,json:{success:false,error:'fixture model error'}});
      }
      return route.fulfill({json:body});
    });
    await page.goto(`${base}/std?tab=tts&projectId=${id}`);
    const model = page.getByRole('combobox',{name:'ElevenLabs 모델'});
    await model.waitFor({timeout:30000});
    assert.equal(await model.inputValue(),'eleven_multilingual_v2');
    await model.selectOption('eleven_v4');
    await page.getByRole('button',{name:'자막 저장 및 TTS 생성',exact:true}).click();
    await page.waitForFunction(()=>document.body.textContent.includes('fixture model error'),null,{timeout:15000}).catch(async error=>{
      console.log(JSON.stringify({requests,errors,text:(await page.locator('body').innerText()).slice(-3500)})); throw error;
    });
    assert.equal(requests.length,1);
    assert.equal(requests[0].model_id,'eleven_v4');
    assert.equal(await model.isEnabled(),true);
    project.project_payload.tts_model_id='eleven_v4';
    await page.reload();
    await model.waitFor(); assert.equal(await model.inputValue(),'eleven_v4');
    await page.screenshot({path:'_dev/artifacts/elevenlabs-v4-comparison/model-selector.png'});
    await page.goto(`${base}/std?tab=subtitle_vrew&projectId=${id}`);
    await model.waitFor(); assert.equal(await model.inputValue(),'eleven_v4');
    assert.deepEqual(errors,[]);
    console.log('PASS: v2 default, v4 selection reaches API, saved model restored, subtitle editor selector, no browser errors');
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
