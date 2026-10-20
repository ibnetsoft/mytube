const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{chromium}=require('@playwright/test');
const root=path.resolve(__dirname,'../..'),id='e9233112-f0d7-4b35-91bf-2f892844eb30';
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 let settings={motion:undefined},version='version-1',models=[],connected=false,savedMotion,savedModel;
 await page.route('http://127.0.0.1:3034/**',async r=>{
  const u=new URL(r.request().url()),p=u.pathname;let data={};
  if(p==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'worker/local_media_status.html'),'utf8').replace('__LOCAL_TOKEN__','fixture')});
  if(p.startsWith('/production-settings.'))return r.fulfill({contentType:p.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(root,'worker/local_production_ui',p.slice(1)))});
  if(p==='/status')data={status:'idle',roles:{}};
  if(p==='/jobs')data={jobs:[]};
  if(p==='/api/local/projects')data={projects:[{id,title:'내장 제작 설정 테스트',employee_email:'fixture@example.invalid'}]};
  if(p===`/api/local/projects/${id}`)data={editable:true,project:{id,title:'내장 제작 설정 테스트',employee_email:'fixture@example.invalid',render_settings:settings,updated_at:version,subtitles:[]},scenes:[{scene_number:1,scene_title:'첫 장면'}]};
  if(p.endsWith('/settings')){const body=r.request().postDataJSON();assert.equal(body.version,version);savedMotion=body.motion;settings={...settings,...(body.motion?{motion:body.motion}:{})};version='version-2';data={render_settings:settings,updated_at:version};}
  if(p.endsWith('/motion-automation'))data={job:null};
  if(p==='/api/local/account-login'){assert.equal(r.request().postDataJSON().password,'fixture-password');connected=true;data={connected:true};}
  if(p==='/api/std/video-models'){
   if(!connected)return r.fulfill({status:401,json:{error:'계정을 연결하세요.'}});
   if(r.request().method()==='POST'){const body=r.request().postDataJSON();savedModel=body;models=[{...body.model,has_key:true}];}
   data={models,active_id:null};
  }
  return r.fulfill({json:data});
 });
 await page.goto('http://127.0.0.1:3034/');await page.locator('#local-production-settings>summary').click();
 await page.getByLabel('제작할 프로젝트',{exact:true}).selectOption(id);
 await page.getByText('제작 방식 선택',{exact:true}).waitFor();await page.getByText('PSD로 AE 장면 연출',{exact:true}).waitFor();
 await page.getByLabel('제출 후 자동 제작 사용',{exact:true}).check();await page.getByLabel('자동 제작 출력 비율',{exact:true}).selectOption('9:16');
 await page.getByRole('button',{name:'제작 모드 저장',exact:true}).click();await page.getByText('AE 제작 설정 저장 완료',{exact:true}).first().waitFor();assert.equal(savedMotion.aspect,'9:16');assert.equal(savedMotion.enabled,true);
 await page.getByRole('button',{name:'영상 생성 모델 · API',exact:true}).click();await page.getByText('기존 영상 API 설정 계정 연결',{exact:true}).click();await page.getByLabel('비밀번호 / PIN',{exact:true}).fill('fixture-password');await page.getByRole('button',{name:'이 워커에서 계정 연결',exact:true}).click();await page.getByText('계정 연결 완료',{exact:true}).waitFor();
 await page.getByLabel('표시 이름',{exact:true}).fill('로컬 설정 모델');await page.getByLabel('모델 ID',{exact:true}).fill('fixture/video');await page.getByLabel('API 주소',{exact:true}).fill('https://queue.fal.run/fixture/video');await page.getByLabel('API 키',{exact:true}).fill('fixture-provider-key');await page.getByRole('button',{name:'모델 등록',exact:true}).click();await page.getByText('설정이 저장되었습니다.',{exact:true}).waitFor();assert.equal(savedModel.api_key,'fixture-provider-key');
 assert.equal(new URL(page.url()).port,'3034');assert.equal(await page.locator('iframe').count(),0);assert.equal(await page.locator('a[href*="worker-studio"]').count(),0);assert.deepEqual(errors,[]);
 // Load the actual script console HTML and scripts against in-memory API fixtures.
 const script=await browser.newPage();script.on('pageerror',e=>errors.push(e.message));let defaults={category:'옛날이야기',production_mode:'standard',script_style:'story',duration_minutes:15,language:'ko',setting_country:'한국',era_region:'현대 지방 소도시',image_style:'실사',image_layer_mode:'hybrid',direction_profile:'auto',required_video_scene_count:18,generate_bgm_prompt:false};
 await script.route('http://127.0.0.1:3033/**',async r=>{const p=new URL(r.request().url()).pathname;
  if(p==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'worker/codex_console/index.html'),'utf8').replace('__LOCAL_TOKEN__','fixture')});
  if(p.startsWith('/assets/')){const name=p.slice(8);return r.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'application/json',body:fs.readFileSync(path.join(root,'worker/codex_console',name))});}
  let data={jobs:[],items:[],categories:[],storage:{connected:true},cloud_summary:{},enabled:true,start_scene:19,max_dialogue_scenes:10};
  if(p==='/api/categories')data={items:[{id:2,name:'옛날이야기'}]};
  if(p==='/api/script-settings'){if(r.request().method()==='POST')defaults=r.request().postDataJSON();data={settings:defaults};}
  return r.fulfill({json:data});
 });
 await script.goto('http://127.0.0.1:3033/');await script.getByRole('button',{name:'⚙  대본 설정',exact:true}).click();
 const form=script.locator('#view-settings form');await form.getByRole('button',{name:'대본 기본값 저장',exact:true}).waitFor();await form.locator('[name=duration_minutes]').fill('22');await form.locator('[name=language]').selectOption('ja');await form.getByRole('button',{name:'대본 기본값 저장',exact:true}).click();await form.getByRole('status').filter({hasText:'저장 완료'}).waitFor();assert.equal(defaults.duration_minutes,22);
 await form.getByRole('button',{name:'저장한 기본값을 신규 생성에 적용',exact:true}).click();assert.equal(await script.locator('#new-form [name=duration]').inputValue(),'22');assert.equal(await script.locator('#new-language').inputValue(),'ja');assert.equal(new URL(script.url()).port,'3033');assert.deepEqual(errors,[]);
 console.log('PASS: native unified worker saves production/model settings in place; native script worker saves defaults and applies them to new generation. No external page or paid generation.');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
