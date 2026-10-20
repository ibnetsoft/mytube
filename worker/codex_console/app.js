'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="local-token"]').content;
let page = 0, hasMore = false, currentSource = null, selectedJob = null, busy = false, catalogRevision = 0;
const titles = {overview:'AI 대본 워커',new:'신규 콘텐츠 생성',repair:'대본 보관함 · 리페어',jobs:'작업 이력 · 결과',preparation:'이미지·좌표·AE 연출 준비',doc:'작업 지침'};
const labels = {completed:'완료',pending:'대기',rendering:'실행 중',canceled:'취소',queued:'대기',running:'실행 중',failed:'실패',interrupted:'중단 · 재시작 필요',awaiting_approval:'검토 대기',approved_pending_repair:'승인 · 적용 대기',ready:'완료',review_pending:'영상 검수 대기',needs_attention:'수정 필요',planned:'계획됨',polling:'감지 중',downloading:'다운로드',preparing:'준비 중',transcoding:'변환 중',idle:'대기',stopped:'중지'};
function displayLabel(value){return String(value??'').replace(/codex/gi,'AI').replace(/supabase/gi,'Database');}
function error(message) { $('error').textContent = displayLabel(message); $('error').hidden = !message; }
function notice(message) { $('notice').textContent = displayLabel(message); $('notice').hidden = !message; }
async function api(path, body) {
  const response = await fetch('/api/'+path,{headers:{'X-Codex-Local':token,'Content-Type':'application/json'},...(body?{method:'POST',body:JSON.stringify(body)}:{})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string'?data.detail: data.error || '요청 실패');
  return data;
}
function element(tag,text,className) { const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(className)node.className=className; return node; }
function shortText(value,max=48){const text=String(value??'');return text.length>max?text.slice(0,max-1)+'…':text;}
function statusText(value){const key=String(value||'').toLowerCase();return labels[key]||labels[value]||String(value||'—');}
function view(name) {
  document.querySelectorAll('main>section').forEach(s=>s.hidden=s.id!=='view-'+name);
  document.querySelectorAll('nav [data-view]').forEach(b=>b.classList.toggle('selected',b.dataset.view===name));
  $('heading').textContent=titles[name];
  if(name==='repair')loadCatalog();
  if(name==='jobs')refresh();

}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
document.querySelectorAll('[data-doc]').forEach(b=>b.addEventListener('click',async()=>{try{const data=await api('docs/'+b.dataset.doc);$('document').textContent=displayLabel(data.text);view('doc');}catch(e){error(e.message);}}));
async function refresh(){try{
  const data=await api('status'); error('');
  $('cli').textContent=data.codex_installed?'CLI 설치 확인':'CLI 없음'; $('cli-note').textContent=data.login_status;
  $('approval-count').textContent=data.cloud_summary?.approvals??data.jobs.filter(j=>j.status==='awaiting_approval').length;
  if(data.cloud_summary)$('job-count').textContent=data.cloud_summary.total??'—';
  $('output').textContent='작업·결과는 Database에 저장되며 로컬 복구본도 함께 보관됩니다.';
  busy=Boolean(data.cloud_summary?.active)||data.jobs.some(j=>['running','queued'].includes(j.status));
  document.querySelector('#new-form button[type=submit]').disabled=busy; $('repair-start').disabled=busy||!currentSource; if($('topic-start'))$('topic-start').disabled=busy;
  if(window.refreshManagement)await window.refreshManagement(data);

}catch(e){error(e.message);}}
async function loadCatalog(){const revision=++catalogRevision;$('catalog-count').textContent='불러오는 중…';try{
  const kind=$('kind').value;const data=await api('catalog?'+new URLSearchParams({kind,page,q:$('search').value}));if(revision!==catalogRevision)return;
  const container=$('catalog');container.replaceChildren();
  for(const item of data.items){const row=element('tr');const title=element('td');title.append(element('strong',item.title),element('small','#'+item.topic_id+(kind==='project'?' · '+item.id:'')));row.append(title);
    row.append(element('td',(item.owner||'미배정')+' · '+item.status),element('td',(item.has_script?'대본 있음':'대본 없음')+' / '+item.scenes+'씬'),element('td',item.image_links+'개 URL'),element('td',item.thumbnail));
    const cell=element('td');const button=element('button','대본 읽기');button.onclick=()=>readSource(item);cell.append(button);row.append(cell);container.append(row);}
  if(!data.items.length){const row=element('tr'),cell=element('td','검색 결과가 없습니다.');cell.colSpan=6;row.append(cell);container.append(row);}
  $('catalog-count').textContent=data.total===null?'전체 건수 미확인':'전체 '+data.total.toLocaleString()+'건';
  hasMore=data.has_more;$('previous').disabled=page===0;$('next').disabled=!hasMore;$('page-label').textContent=(page+1)+' 페이지';error('');
}catch(e){if(revision!==catalogRevision)return;$('catalog-count').textContent='조회 실패';$('catalog').replaceChildren();error(e.message);}}
let sourceRevision=0;
async function readSource(item){const revision=++sourceRevision;currentSource=null;$('source-panel').hidden=true;try{
  const data=await api('source/'+item.kind+'/'+item.id);if(revision!==sourceRevision)return;currentSource=data;
  $('source-title').textContent=data.summary.title;$('source-identity').textContent=(item.kind==='project'?'프로젝트 ':'공용 토픽 ')+item.id+' · '+(item.owner||'미배정')+(data.summary.protected?' · 제출/보호 상태: 수정안만 생성 가능':'');
  $('source-script').textContent=data.script||'저장된 대본이 없습니다.';$('source-panel').hidden=false;$('repair-start').disabled=busy||!data.script;
  $('source-panel').scrollIntoView({behavior:'smooth',block:'start'});
}catch(e){error(e.message);}}
$('search-button').onclick=()=>{page=0;loadCatalog();};$('search').onkeydown=e=>{if(e.key==='Enter'){$('search-button').click();}};
$('kind').onchange=()=>{page=0;currentSource=null;sourceRevision++;$('source-panel').hidden=true;loadCatalog();};
$('previous').onclick=()=>{if(page>0){page--;loadCatalog();}};$('next').onclick=()=>{if(hasMore){page++;loadCatalog();}};
// Full-page refresh with draft restoration is wired by refresh.js.
async function start(body){if(busy)return;busy=true;error('');try{const result=await api('jobs',body);notice('로컬 작업을 시작했습니다. 기존 운영 대본은 변경하지 않습니다.');view('jobs');await showJob(result.id);}catch(e){error(e.message);}finally{await refresh();}}
const defaultCountryByLanguage = {ko:'한국',en:'미국',ja:'일본',es:'스페인'};
const langNames = {ko:'한국어',en:'영어',ja:'일본어',es:'스페인어'};
window.newCountryOverridden = false;
window.updateNewSettingSummary = function() {
  const form = $('new-form');
  if (!form) return {};
  const lang = form.elements.language?.value || 'ko';
  const countrySelect = $('new-country');
  const customCountry = $('new-custom-country');
  let country = countrySelect.value === 'custom' ? (customCountry.value.trim() || '직접 입력') : countrySelect.value;
  const era = form.elements.era_region?.value.trim() || '현대 지방 소도시';
  const style = form.elements.image_style?.value || '실사';
  const summary = `${langNames[lang] || lang} · ${country} ${era} · ${style}`;
  const el = $('new-setting-summary');
  if (el) el.textContent = summary;
  return { language: lang, setting_country: country, era_region: era, image_style: style, summary_label: summary };
};
if ($('new-language')) {
  $('new-language').onchange = e => {
    const lang = e.target.value;
    if (!window.newCountryOverridden) {
      const def = defaultCountryByLanguage[lang] || '한국';
      $('new-country').value = def;
      $('new-custom-country').style.display = 'none';
    }
    window.updateNewSettingSummary();
  };
  $('new-country').onchange = e => {
    window.newCountryOverridden = true;
    const isCustom = e.target.value === 'custom';
    $('new-custom-country').style.display = isCustom ? 'block' : 'none';
    if (isCustom) $('new-custom-country').focus();
    window.updateNewSettingSummary();
  };
  $('new-custom-country').oninput = window.updateNewSettingSummary;
  $('new-era').oninput = window.updateNewSettingSummary;
  $('new-style').onchange = window.updateNewSettingSummary;
  window.updateNewSettingSummary();
}
function syncNonverbalMode(){
 const enabled=$('production-mode').value==='nonverbal_preschool',form=$('new-form');
 form.elements.duration.max=enabled?'10':'60';
 if(enabled){
  if(Number(form.elements.duration.value)>10)form.elements.duration.value='3';
  $('new-style').value='애니메이션';$('new-script-style').value='nonverbal_preschool';
  $('image-layer-mode').value='full_psd';form.elements.required_video_scene_count.value='18';
 }else if($('new-script-style').value==='nonverbal_preschool'){$('new-script-style').value='story';}
 let help=$('nonverbal-help');if(!help){help=element('p','대사·나레이션 없이 행동 이야기와 재사용 부품, 시간별 관절 연출을 만듭니다. 실제 원화·음악·효과음·AE 결과 검수는 후속 단계입니다.','callout');help.id='nonverbal-help';form.prepend(help)}
 help.hidden=!enabled;window.updateNewSettingSummary();
}
$('production-mode').onchange=()=>{syncNonverbalMode();if($('production-mode').value==='moving_comic'&&$('new-style').value==='실사'){$('new-style').value='웹툰';window.updateNewSettingSummary();}};
if($('image-layer-mode')){
  const grid=$('image-layer-mode').closest('.form-grid');
  const makeRangeInput=(name,text,placeholder)=>{
    const label=element('label',text),input=element('input');
    input.name=name;input.type='number';input.min='1';input.max='999';input.placeholder=placeholder;
    label.append(input);grid.append(label);
  };
  makeRangeInput('image_layer_scene_start','레이어 생성 시작 씬','예: 19');
  makeRangeInput('image_layer_scene_end','레이어 생성 종료 씬','예: 35');
  const help=element('p','선택 범위의 씬은 배경과 전경을 독립 PNG 레이어로 생성해 PSD로 준비합니다. 범위를 비우면 기존 레이어 모드만 적용됩니다.','muted');
  grid.after(help);
}
$('new-form').onsubmit=e=>{
  e.preventDefault();
  const form=new FormData(e.target);
  const category=form.get('custom_category').trim()||form.get('category');
  if(!category){error('카테고리를 입력하세요.');return;}
  const setting = window.updateNewSettingSummary();
  if(!confirm('AI 신규 대본 생성기를 실행할까요? CLI 사용량이 발생하며 결과는 Database에 저장합니다.'))return;
  start({
    mode:'new',
    production_mode:form.get('production_mode')||'standard',youtube_url:form.get('youtube_url')||'',
    direction_profile:form.get('direction_profile')||'auto',
    image_layer_mode:form.get('image_layer_mode')||'hybrid',
    image_layer_scene_start:form.get('image_layer_scene_start')?Number(form.get('image_layer_scene_start')):null,
    image_layer_scene_end:form.get('image_layer_scene_end')?Number(form.get('image_layer_scene_end')):null,
    required_video_scene_count:Number(form.get('required_video_scene_count')??18),
    title:form.get('title'),
    category,
    category_id:form.get('custom_category').trim()?'':$('category').selectedOptions[0]?.dataset.id||'',
    script_style:form.get('script_style')||'story',
    duration_minutes:Number(form.get('duration')),
    language:setting.language,
    setting_country:setting.setting_country,
    era_region:setting.era_region,
    image_style:setting.image_style,
    generate_bgm_prompt:form.get('generate_bgm_prompt')==='on',
    notes:form.get('notes')
  });
};
$('repair-start').onclick=()=>{if(!currentSource||busy)return;if(!confirm('이 대본의 Astra 수정안을 생성할까요? 원본은 보존하고 결과를 Database에 저장합니다.'))return;start({production_mode:$('repair-production-mode').value,mode:'repair',kind:currentSource.kind,source_id:currentSource.id,notes:$('repair-notes').value});};
let resultRevision=0;
async function showJob(id,origin='dedicated'){const revision=++resultRevision;try{
  const data=await api(origin==='legacy'?'history/legacy/'+id:'jobs/'+id);
  if(revision!==resultRevision)return;
  selectedJob={...data.job,origin};
  $('result').hidden=false;
  $('result-title').textContent=data.job.title;
  let statusText = (labels[data.job.status]||data.job.status)+' · '+data.job.stage+(data.job.error?' · '+data.job.error:'');
  if(data.result_data?.production_mode==='nonverbal_preschool')statusText+=' · 논버벌 행동 기획 · 발화 없음';
  const directionProfile=data.result_data?.structure?.direction_profile;
  if(directionProfile?.label)statusText+=' · 연출 '+directionProfile.label;
  if(data.sfx_summary&&data.sfx_summary.status!=='not_run') statusText+=' · 효과음 '+data.sfx_summary.status+' / '+data.sfx_summary.count+'개 / 재검토 '+data.sfx_summary.review_count+'개';
  if(data.result_data?.comic_plan){const plan=data.result_data.comic_plan;statusText+=' · 무빙툰 '+plan.pages.length+'페이지 / 영상화 '+plan.scenes.filter(s=>s.motion==='video').length+'씬';}
  $('result-status').textContent=displayLabel(statusText);
  const settingBadge = $('result-setting-badge');
  const cs = data.content_setting || data.job.content_setting;
  if (settingBadge && cs) {
    settingBadge.hidden = false;
    settingBadge.replaceChildren(document.createTextNode('배경 설정: '),element('strong',cs.summary_label || (cs.language + ' · ' + cs.setting_country)));
  } else if (settingBadge) {
    settingBadge.hidden = true;
  }
  $('original').textContent=data.original||'신규 생성 — 원본 없음';
  $('candidate').textContent=data.script||'아직 저장된 결과가 없습니다.';
  $('remaining').replaceChildren(...data.remaining.map(text=>element('li',text)));
  $('approve').hidden=origin==='legacy'||data.job.status!=='awaiting_approval';
  if(window.renderManagementResult)window.renderManagementResult(data,origin);
  if(window.renderGroundedResult)window.renderGroundedResult(data);
  if(window.renderTopicResult)window.renderTopicResult(data);
}catch(e){error(e.message);}}
$('approve').onclick=async()=>{if(!selectedJob||!confirm('표시된 대본 버전에 승인 기록을 남길까요? 운영 대본 적용은 실행하지 않습니다.'))return;try{await api('jobs/'+selectedJob.id+'/approve',{candidate_hash:selectedJob.candidate_hash});notice('승인 기록을 저장했습니다. 연관 자료 검증과 운영 적용은 남아 있습니다.');await showJob(selectedJob.id,selectedJob.origin);refresh();}catch(e){error(e.message);}};
window.categoriesReady=api('categories').then(data=>{const options=data.items.map(c=>{const o=element('option',c.name);o.value=c.name;o.dataset.id=c.id;return o;});const custom=element('option','직접 입력');custom.value='';$('category').replaceChildren(...options,custom);}).catch(e=>error(e.message));
refresh();setInterval(()=>{if(document.hidden)return;refresh();if(selectedJob&&!$('view-jobs').hidden)showJob(selectedJob.id,selectedJob.origin);},10000);

if ($('new-script-style')) $('new-script-style').onchange = () => {
  if($('new-script-style').value==='nonverbal_preschool'){$('production-mode').value='nonverbal_preschool';syncNonverbalMode();return;}
  if($('production-mode').value==='nonverbal_preschool'){$('production-mode').value='standard';syncNonverbalMode();}

  if ($('new-script-style').value === 'japanese_domestic_drama') {
    $('new-language').value='ja';$('new-country').value='일본';$('new-custom-country').style.display='none';
    $('production-mode').value='standard';
    $('direction-profile').value='standard';$('new-style').value='jp_domestic_watercolor';
    $('new-era').value='현대 일본 · 도쿄 근교 주거지역';$('new-form').elements.required_video_scene_count.value='18';$('new-form').elements.generate_bgm_prompt.checked=true;
    window.categoriesReady.then(()=>{$('category').value='일본사건'});
  } else if ($('new-script-style').value === 'japanese_historical_documentary') {
    $('new-language').value = 'ja';
    $('new-country').value = '일본';
    $('new-custom-country').style.display = 'none';
    $('new-form').elements.duration.value = '30';
    $('production-mode').value = 'standard';
    $('direction-profile').value = 'standard';
    $('new-style').value = 'sumi_e_ukiyo_e';
    if ($('new-era').value === '현대 지방 소도시') $('new-era').value = '주제 인물의 실제 생존 시대·지역';
  }
  window.updateNewSettingSummary();
};

async function loadMouthPolicy(){
  try { const p=await api('mouth-policy'); $('mouth-enabled').checked=p.enabled;
    $('mouth-start').value=p.start_scene; $('mouth-count').value=p.max_dialogue_scenes;
  } catch(e){error(e.message);}
}
$('mouth-policy-form').addEventListener('submit',async event=>{
  event.preventDefault(); const button=event.currentTarget.querySelector('button'); button.disabled=true;
  try { await api('mouth-policy',{enabled:$('mouth-enabled').checked,start_scene:Number($('mouth-start').value),max_dialogue_scenes:Number($('mouth-count').value)});
    $('mouth-policy-status').textContent=' 저장됨 · 다음 이미지 작업부터 적용';
  } catch(e){error(e.message);} finally {button.disabled=false;}
});
loadMouthPolicy();
