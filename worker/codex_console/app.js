'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="local-token"]').content;
let page = 0, hasMore = false, currentSource = null, selectedJob = null, busy = false, catalogRevision = 0;
const titles = {overview:'AI 대본 워커',new:'신규 콘텐츠 생성',repair:'대본 보관함 · 리페어',jobs:'작업 이력 · 결과',ae:'AE 하이라이트',doc:'작업 지침'};
const labels = {completed:'완료',pending:'대기',rendering:'실행 중',canceled:'취소',queued:'대기',running:'실행 중',failed:'실패',interrupted:'중단 · 재시작 필요',awaiting_approval:'검토 대기',approved_pending_repair:'승인 · 적용 대기',ready:'완료',planned:'계획됨',polling:'감지 중',downloading:'다운로드',preparing:'준비 중',transcoding:'변환 중',idle:'대기',stopped:'중지'};
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
  if(name==='ae')loadAeHighlight();
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
document.querySelectorAll('[data-doc]').forEach(b=>b.addEventListener('click',async()=>{try{const data=await api('docs/'+b.dataset.doc);$('document').textContent=displayLabel(data.text);view('doc');}catch(e){error(e.message);}}));
function aeTableEmpty(tbody,message,colSpan){
  const row=element('tr'),cell=element('td',message,'muted');
  cell.colSpan=colSpan;row.append(cell);tbody.replaceChildren(row);
}
function aeDirectionText(item){
  const targets=Array.isArray(item.targets)?item.targets:[];
  const targetText=targets.map(target=>target&&target.type).filter(Boolean).slice(0,2).join(', ');
  return [item.mood,item.camera,targetText].filter(Boolean).map(value=>shortText(value,24)).join(' · ')||'—';
}
function aePresetText(item){
  const kind=item.plan_kind==='motion'?'일반 모션':'하이라이트';
  return `${kind} · ${item.preset||'—'}`;
}
function aeJobRow(job){
  const row=element('tr');
  const title=element('td');
  title.append(element('strong',shortText(job.title||job.topic_id,48)),element('small',job.topic_id||''));
  row.append(title,element('td',String(job.scene_number||'—')),element('td',aePresetText(job)),element('td',aeDirectionText(job)),element('td',shortText((job.source?.bucket||'')+'/'+(job.source?.path||''),72)));
  return row;
}
function aeSceneRow(scene){
  const row=element('tr');
  row.append(element('td',shortText(scene.title||scene.topic_id,48)),element('td',String(scene.scene_number||'—')),element('td',aePresetText(scene)),element('td',aeDirectionText(scene)),element('td',statusText(scene.status)));
  const result=element('td');
  if(scene.media_url){const link=element('a','보기');link.href=scene.media_url;link.target='_blank';link.rel='noreferrer';result.append(link);}
  else result.textContent=shortText(scene.error||'—',44);
  row.append(result);
  return row;
}
async function loadAeHighlight(){
  try{
    const data=await api('ae-highlight/status?limit=40');
    const state=data.state||{},summary=data.summary||{},cap=data.capability||{};
    const current=state.current_job&&typeof state.current_job==='object'?state.current_job:null;
    const status=statusText(state.status||'stopped');
    const capability=Boolean(cap.afterfx_exists&&cap.aerender_exists);
    $('ae-worker-status').textContent=status;
    $('ae-state').textContent=status;
    $('ae-state-note').textContent=state.pid?`PID ${state.pid}`:'프로세스 없음';
    $('ae-candidates').textContent=String(data.candidate_count??0);
    $('ae-scan-note').textContent=`${data.topics_scanned??0}개 토픽 스캔`;
    $('ae-planned').textContent=String(summary.planned??0);
    $('ae-plan-note').textContent=`완료 ${summary.ready||0} · 진행 ${summary.rendering||0} · 실패 ${summary.failed||0}`;
    $('ae-capability').textContent=capability?'OK':'확인 필요';
    $('ae-path').textContent=cap.aerender_path||data.error||'aerender 경로 없음';
    $('ae-current').textContent=current?`현재 작업: ${current.project_name||current.job_id||'—'} · 씬 ${current.scene_number||'—'} · ${current.preset||'—'} · ${current.progress_message||''}`:(state.last_error?`최근 오류: ${displayLabel(state.last_error)}`:'현재 진행 중인 AE 작업이 없습니다.');
    const jobsBody=$('ae-jobs');
    const jobRows=(data.jobs||[]).map(aeJobRow);
    if(jobRows.length)jobsBody.replaceChildren(...jobRows);else aeTableEmpty(jobsBody,'렌더 대기 중인 AE 장면이 없습니다.',5);
    const scenesBody=$('ae-scenes');
    const sceneRows=(summary.recent||[]).map(aeSceneRow);
    if(sceneRows.length)scenesBody.replaceChildren(...sceneRows);else aeTableEmpty(scenesBody,'아직 AE 계획 장면이 없습니다.',6);
    error('');
  }catch(e){error(e.message);}
}
async function refresh(){try{
  const data=await api('status'); error('');
  $('cli').textContent=data.codex_installed?'CLI 설치 확인':'CLI 없음'; $('cli-note').textContent=data.login_status;
  $('approval-count').textContent=data.cloud_summary?.approvals??data.jobs.filter(j=>j.status==='awaiting_approval').length;
  if(data.cloud_summary)$('job-count').textContent=data.cloud_summary.total??'—';
  $('output').textContent='작업·결과는 Database에 저장되며 로컬 복구본도 함께 보관됩니다.';
  busy=Boolean(data.cloud_summary?.active)||data.jobs.some(j=>['running','queued'].includes(j.status));
  document.querySelector('#new-form button[type=submit]').disabled=busy; $('repair-start').disabled=busy||!currentSource; if($('topic-start'))$('topic-start').disabled=busy;
  if(window.refreshManagement)await window.refreshManagement(data);
  if(!$('view-ae').hidden)await loadAeHighlight();
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
$('production-mode').onchange=()=>{if($('production-mode').value==='moving_comic'&&$('new-style').value==='실사'){$('new-style').value='웹툰';window.updateNewSettingSummary();}};
$('new-form').onsubmit=e=>{
  e.preventDefault();
  const form=new FormData(e.target);
  const category=form.get('custom_category').trim()||form.get('category');
  if(!category){error('카테고리를 입력하세요.');return;}
  const setting = window.updateNewSettingSummary();
  if(!confirm('AI 신규 대본 생성기를 실행할까요? CLI 사용량이 발생하며 결과는 Database에 저장합니다.'))return;
  start({
    mode:'new',
    production_mode:form.get('production_mode')||'standard',
    title:form.get('title'),
    category,
    category_id:form.get('custom_category').trim()?'':$('category').selectedOptions[0]?.dataset.id||'',
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
if($('ae-refresh'))$('ae-refresh').onclick=loadAeHighlight;
if($('ae-start'))$('ae-start').onclick=async()=>{try{await api('ae-highlight/start',{});notice('AE 워커 시작을 요청했습니다.');await loadAeHighlight();}catch(e){error(e.message);}};
if($('ae-stop'))$('ae-stop').onclick=async()=>{try{await api('ae-highlight/stop',{});notice('AE 워커 중지를 요청했습니다.');await loadAeHighlight();}catch(e){error(e.message);}};
let resultRevision=0;
async function showJob(id,origin='dedicated'){const revision=++resultRevision;try{
  const data=await api(origin==='legacy'?'history/legacy/'+id:'jobs/'+id);
  if(revision!==resultRevision)return;
  selectedJob={...data.job,origin};
  $('result').hidden=false;
  $('result-title').textContent=data.job.title;
  let statusText = (labels[data.job.status]||data.job.status)+' · '+data.job.stage+(data.job.error?' · '+data.job.error:'');
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
