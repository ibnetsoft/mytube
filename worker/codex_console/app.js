'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="local-token"]').content;
const consoleSearchKey='codex-script-console-search-v1',consoleSearchListeners=new Set();
let consoleSearchValue='';
try{consoleSearchValue=sessionStorage.getItem(consoleSearchKey)||'';}catch{}
window.consoleSearch={
  get:()=>consoleSearchValue,
  set(value){
    value=String(value??'');
    consoleSearchValue=value;
    try{sessionStorage.setItem(consoleSearchKey,value);}catch{}
    for(const listener of consoleSearchListeners)listener(value);
  },
  subscribe(listener){consoleSearchListeners.add(listener);listener(consoleSearchValue);return()=>consoleSearchListeners.delete(listener);}
};
function bindConsoleSearch(input,onChange){
  input.addEventListener('input',()=>window.consoleSearch.set(input.value));
  return window.consoleSearch.subscribe(value=>{input.value=value;onChange?.();});
}
let page = 0, hasMore = false, currentSource = null, selectedJob = null, busy = false, catalogRevision = 0;
const titles = {overview:'토픽별 제작 현황',chat:'Codex 채팅',settings:'대본워커 설정',new:'신규 콘텐츠 생성',repair:'대본 보관함 · 리페어',jobs:'작업 이력 · 결과',preparation:'이미지·좌표·AE 연출 준비',doc:'작업 지침'};
const labels = {completed:'완료',pending:'대기',rendering:'실행 중',canceled:'취소',queued:'대기',running:'실행 중',failed:'실패',interrupted:'중단 · 재시작 필요',awaiting_approval:'검토 대기',approved_pending_repair:'승인 · 적용 대기',ready:'완료',review_pending:'영상 검수 대기',needs_attention:'수정 필요',planned:'계획됨',polling:'감지 중',downloading:'다운로드',preparing:'준비 중',transcoding:'변환 중',idle:'대기',stopped:'중지'};
function displayLabel(value){return String(value??'').replace(/codex/gi,'AI').replace(/supabase/gi,'Database');}
function error(message) { $('error').textContent = displayLabel(message); $('error').hidden = !message; }
function notice(message) { $('notice').textContent = displayLabel(message); $('notice').hidden = !message; }
async function api(path, body) {
  let response;
  try { response = await fetch('/api/'+path,{headers:{'X-Codex-Local':token,'Content-Type':'application/json'},...(body?{method:'POST',body:JSON.stringify(body)}:{})}); }
  catch { throw new Error('대본워커와 연결되지 않았습니다. 워커 상태를 확인하고 새로고침해 주세요.'); }
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`서버 응답을 읽지 못했습니다 (HTTP ${response.status}). 워커 상태를 확인해 주세요.`); }
  if (!response.ok) throw new Error(typeof data.detail === 'string'?data.detail: data.error || '요청 실패');
  return data;
}
function element(tag,text,className) { const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(className)node.className=className; return node; }
// Shared by catalog, history, results, submissions and the preparation panel.
const titleRequests=new Map();
let titleFlushTimer;
function titleRecord(item){
  const kind=item.source_kind||item.kind;
  return {title:String(item.title||''),topic_id:item.topic_queue_id??item.topic_id??(kind==='topic'?(item.source_id||item.id):null),
    project_id:item.project_id||(kind==='project'?(item.source_id||item.id):null)};
}
function decorateTitle(node,item){
  const record=titleRecord(item),key=JSON.stringify(record);
  const update=value=>{
    const number=value.topic_id??record.topic_id;
    node.replaceChildren(document.createTextNode((/^\d+$/.test(String(number||''))?'#'+number+' · ':'')+record.title));
    if(value.title_ko)node.append(element('small',value.title_ko,'title-ko'));
    else if(value.status==='running')node.append(element('small','한국어 번역 대기 중 · 로컬 Codex','title-ko'));
    else if(value.status==='failed')node.append(element('small','한국어 번역을 불러오지 못했습니다.','title-ko'));
    node.dispatchEvent(new Event('console-title-updated',{bubbles:true}));
  };
  let entry=titleRequests.get(key);
  if(!entry){entry={record,listeners:new Set(),value:{status:'running'}};titleRequests.set(key,entry);}
  entry.listeners.add(node);node._titleKey=key;node._titleUpdate=update;update(entry.value);
  clearTimeout(titleFlushTimer);titleFlushTimer=setTimeout(flushTitles,40);
  return node;
}
function titleNode(item,tag='strong'){return decorateTitle(element(tag,undefined,'localized-title'),item);}
async function flushTitles(){
  const entries=[...titleRequests.values()].filter(e=>!e.loading&&(!e.value.status||e.value.status==='running')&&[...e.listeners].some(n=>n.isConnected)).slice(0,100);
  if(!entries.length)return;
  entries.forEach(e=>e.loading=true);
  try{
    const data=await api('title-display',{items:entries.map(e=>e.record)});
    entries.forEach((entry,i)=>{entry.value=data.items[i];});
  }catch{entries.forEach(e=>e.value={status:'failed'});}
  finally{
    for(const entry of entries){entry.loading=false;for(const node of entry.listeners){if(node.isConnected&&node._titleKey===JSON.stringify(entry.record))node._titleUpdate(entry.value);else entry.listeners.delete(node);}}
    if([...titleRequests.values()].some(e=>e.value.status==='running')){clearTimeout(titleFlushTimer);titleFlushTimer=setTimeout(flushTitles,2500);}
  }
}
window.decorateConsoleTitle=decorateTitle;
function shortText(value,max=48){const text=String(value??'');return text.length>max?text.slice(0,max-1)+'…':text;}
function statusText(value){const key=String(value||'').toLowerCase();return labels[key]||labels[value]||String(value||'—');}
function view(name) {
  document.querySelectorAll('main>section').forEach(s=>s.hidden=s.id!=='view-'+name);
  document.querySelectorAll('nav [data-view]').forEach(b=>b.classList.toggle('selected',b.dataset.view===name));
  $('heading').textContent=titles[name];
  window.saveConsoleViewState?.(name);
  if(name==='overview')loadProductionOverview();
  if(name==='chat')loadChat();
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
  busy=Boolean(data.local_busy);
  document.querySelector('#new-form button[type=submit]').disabled=busy; $('repair-start').disabled=busy||!currentSource; if($('topic-start'))$('topic-start').disabled=busy;
  if(window.refreshManagement)await window.refreshManagement(data);

}catch(e){error(e.message);}}
async function loadCatalog(){const revision=++catalogRevision;$('catalog-count').textContent='불러오는 중…';try{
  const kind=$('kind').value;const data=await api('catalog?'+new URLSearchParams({kind,page,q:$('search').value}));if(revision!==catalogRevision)return;
  const container=$('catalog');container.replaceChildren();
  for(const item of data.items){const row=element('tr');const title=element('td');title.append(titleNode(item));if(kind==='project')title.append(element('small',item.id));row.append(title);
    row.append(element('td',(item.owner||'미배정')+' · '+item.status),element('td',(item.has_script?'대본 있음':'대본 없음')+' / '+item.scenes+'씬'),element('td',item.image_links+'개 URL'),element('td',item.thumbnail));
    const cell=element('td');const button=element('button','대본 읽기');button.onclick=()=>readSource(item);cell.append(button);row.append(cell);container.append(row);}
  if(!data.items.length){const row=element('tr'),cell=element('td','검색 결과가 없습니다.');cell.colSpan=6;row.append(cell);container.append(row);}
  $('catalog-count').textContent=data.total===null?'전체 건수 미확인':'전체 '+data.total.toLocaleString()+'건';
  hasMore=data.has_more;$('previous').disabled=page===0;$('next').disabled=!hasMore;$('page-label').textContent=(page+1)+' 페이지';error('');
}catch(e){if(revision!==catalogRevision)return;$('catalog-count').textContent='조회 실패';$('catalog').replaceChildren();error(e.message);}}
let sourceRevision=0;
async function readSource(item){const revision=++sourceRevision;currentSource=null;$('source-panel').hidden=true;try{
  const data=await api('source/'+item.kind+'/'+item.id);if(revision!==sourceRevision)return;currentSource=data;
  decorateTitle($('source-title'),data.summary);$('source-identity').textContent=(item.kind==='project'?'프로젝트 ':'공용 토픽 ')+item.id+' · '+(item.owner||'미배정')+(data.summary.protected?' · 제출/보호 상태: 수정안만 생성 가능':'');
  $('source-script').textContent=data.script||'저장된 대본이 없습니다.';$('source-panel').hidden=false;$('repair-start').disabled=busy||!data.script;
  $('source-panel').scrollIntoView({behavior:'smooth',block:'start'});
}catch(e){error(e.message);}}
$('search-button').onclick=()=>{page=0;loadCatalog();};$('search').onkeydown=e=>{if(e.key==='Enter'){$('search-button').click();}};
bindConsoleSearch($('search'),()=>{page=0;catalogRevision++;});
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
  const allParallax=form.elements.parallax_mode?.value==='all_scenes';
  if(allParallax){form.elements.required_video_scene_count.value='0';form.elements.image_layer_mode.value='full_psd';}
  form.elements.required_video_scene_count.readOnly=allParallax;
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
 form.elements.duration.max=enabled?'10':'180';
 if(enabled){
  if(Number(form.elements.duration.value)>10)form.elements.duration.value='3';
  $('new-style').value='애니메이션';$('new-script-style').value='nonverbal_preschool';
  $('image-layer-mode').value='full_psd';form.elements.required_video_scene_count.value='0';
 }else if($('new-script-style').value==='nonverbal_preschool'){$('new-script-style').value='story';}
 let help=$('nonverbal-help');if(!help){help=element('p','대사·나레이션 없이 행동 이야기와 재사용 부품, 시간별 관절 연출을 만듭니다. 실제 원화·음악·효과음·AE 결과 검수는 후속 단계입니다.','callout');help.id='nonverbal-help';form.prepend(help)}
 help.hidden=!enabled;window.updateNewSettingSummary();
}
$('production-mode').onchange=()=>{syncNonverbalMode();if($('production-mode').value==='moving_comic'&&$('new-style').value==='실사'){$('new-style').value='웹툰';window.updateNewSettingSummary();}};
if($('image-layer-mode')){
  const grid=$('image-layer-mode').closest('.form-grid');
  const makeRangeInput=(name,text,placeholder)=>{
    const label=element('label',text),input=element('input');
    input.name=name;input.type='number';input.min='1';input.max='999';input.placeholder=placeholder;input.value='';
    label.append(input);grid.append(label);
  };
  makeRangeInput('image_layer_scene_start','레이어 생성 시작 씬','예: 19');
  makeRangeInput('image_layer_scene_end','레이어 생성 종료 씬','예: 35');
  const help=element('p','선택 범위에서 배경과 인물을 따로 만들고 입모양·눈 깜빡임·패럴럭스 등 효과를 집중합니다. 범위 밖은 씬당 이미지 한 장을 사용합니다.','muted');
  grid.after(help);
  window.layeredEffectScopeReady=false;
  fetch('/health',{cache:'no-store'}).then(r=>r.json()).then(status=>{
    if(status.effect_scope_version!==1)return;
    window.layeredEffectScopeReady=true;
    const start=grid.querySelector('[name=image_layer_scene_start]'),end=grid.querySelector('[name=image_layer_scene_end]');
    help.textContent='기본값: 1~18씬 이미지 1장, 19~50씬 레이어·입모양·패럴럭스 등 AE 연출, 51씬부터 이미지 1장과 줌·좌우 이동 및 문맥에 맞는 씬 전환. 느린 줌은 사용하지 않습니다.';
  }).catch(()=>{});
}
$('new-form').noValidate=true;
document.querySelector('#new-form button[type=submit]').textContent='설정 확인 후 대본 생성';
$('new-form').onsubmit=async e=>{
  e.preventDefault();
  if(!await window.reviewScriptSettings(e.target,()=>!busy)||busy)return;
  const form=new FormData(e.target);
  const category=form.get('custom_category').trim()||form.get('category');
  if(!category){error('카테고리를 입력하세요.');return;}
  const setting = window.updateNewSettingSummary();
  const stateCount=Number(form.get('character_state_count')||0);
  const stateStart=form.get('character_state_scene_start')?Number(form.get('character_state_scene_start')):null;
  const stateEnd=form.get('character_state_scene_end')?Number(form.get('character_state_scene_end')):null;
  if(stateCount&&(!Number.isInteger(stateStart)||!Number.isInteger(stateEnd)||stateStart<1||stateEnd>999||stateStart>stateEnd)){error('장면 상태 레이어의 시작·종료 씬을 올바르게 입력하세요.');return;}
  start({
    mode:'new',settings_confirmed:true,
    concentrated_scene_effects:Boolean(form.get('image_layer_scene_start')) && Boolean(form.get('image_layer_scene_end')) && stateCount===0 && (form.get('production_mode')||'standard')==='standard' && (form.get('parallax_mode')||'selective')==='selective' && (form.get('image_layer_mode')||'hybrid')==='hybrid',
    production_mode:form.get('production_mode')||'standard',youtube_url:form.get('youtube_url')||'',
    direction_profile:form.get('direction_profile')||'auto',
    parallax_mode:form.get('parallax_mode')||'selective',
    image_layer_mode:form.get('image_layer_mode')||'hybrid',
    character_state_count:stateCount,
    character_state_scene_start:stateStart,
    character_state_scene_end:stateEnd,
    image_layer_scene_start:form.get('image_layer_scene_start')?Number(form.get('image_layer_scene_start')):null,
    image_layer_scene_end:form.get('image_layer_scene_end')?Number(form.get('image_layer_scene_end')):null,
    required_video_scene_count:Number(form.get('required_video_scene_count')??0),
    title:form.get('title'),
    category,
    category_id:form.get('custom_category').trim()?'':$('category').selectedOptions[0]?.dataset.id||'',
    script_style:form.get('script_style')||'story',
    duration_minutes:Number(form.get('duration')),
    chapter_minutes:Number(form.get('chapter_minutes')||15),
    language:setting.language,
    setting_country:setting.setting_country,
    era_region:setting.era_region,
    image_style:setting.image_style,
    generate_publish_package:form.get('generate_publish_package')==='on',
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
  decorateTitle($('result-title'),{...data.job,source_kind:data.source_link?.kind||data.job.kind,source_id:data.source_link?.id||data.job.source_id});
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
window.categoriesReady=api('categories').then(data=>{
  const excluded=new Set(['경제','노후금융']);
  const categories=data.items.filter(c=>!excluded.has(c.name));
  for(const name of ['판타지/SF','일상/웹툰','지식/미스터리','힐링/동화']){
    if(!categories.some(c=>c.name===name))categories.push({name,id:''});
  }
  const options=categories.map(c=>{const o=element('option',c.name);o.value=c.name;o.dataset.id=c.id;return o;});
  const custom=element('option','직접 입력');custom.value='';
  $('category').replaceChildren(...options,custom);
}).catch(e=>error(e.message));
refresh();setInterval(()=>{if(document.hidden)return;refresh();if(selectedJob&&!$('view-jobs').hidden)showJob(selectedJob.id,selectedJob.origin);},10000);

if ($('new-script-style')) $('new-script-style').onchange = () => {
  if($('new-script-style').value==='nonverbal_preschool'){$('production-mode').value='nonverbal_preschool';syncNonverbalMode();return;}
  if($('production-mode').value==='nonverbal_preschool'){$('production-mode').value='standard';syncNonverbalMode();}

  if ($('new-script-style').value === 'japanese_domestic_drama') {
    $('new-language').value='ja';$('new-country').value='일본';$('new-custom-country').style.display='none';
    $('production-mode').value='standard';
    $('direction-profile').value='standard';$('new-style').value='jp_domestic_watercolor';
    $('new-era').value='현대 일본 · 도쿄 근교 주거지역';$('new-form').elements.required_video_scene_count.value='0';$('new-form').elements.generate_bgm_prompt.checked=true;
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

// A long tale is still one story and one final project; chapters are recovery boundaries.
const storyChapterLabel=element('label','장편 야담 · 장별 목표 (분)'),storyChapterSize=element('select');
storyChapterSize.name='chapter_minutes';storyChapterSize.id='story-chapter-minutes';
for(const value of [15,20]){const option=element('option',value+'분');option.value=String(value);storyChapterSize.append(option);}
storyChapterSize.value='15';storyChapterLabel.append(storyChapterSize);
$('new-form').elements.duration.closest('label').after(storyChapterLabel);
const storyHelp=element('p','일본어 · 이야기 · 기존 영상에서 61~180분을 입력하면 한 편의 장편 야담으로 제작합니다. 전체 줄거리·인물·복선을 먼저 계획하고 장별 검토본을 저장합니다. 중단된 작업은 결과에서 완료한 장을 보존해 이어서 제작할 수 있습니다. 실제 영상 길이는 음성 제작 후 확인합니다.','callout');
storyChapterLabel.after(storyHelp);
const storyPreset=element('button','3시간 일본 야담 설정');storyPreset.type='button';
storyPreset.onclick=()=>{
  const form=$('new-form');form.elements.duration.value='180';form.elements.duration.max='180';
  form.elements.chapter_minutes.value='15';$('new-language').value='ja';$('new-country').value='일본';
  $('new-custom-country').style.display='none';$('new-script-style').value='story';$('production-mode').value='standard';
  $('direction-profile').value='japanese_folktale';$('new-era').value='에도 시대 일본';window.newCountryOverridden=true;
  const category=[...$('category').options].find(option=>/日本昔話|일본.*(야담|옛날|이야기)/.test(option.textContent));
  if(category){$('category').value=category.value;form.elements.custom_category.value='';}else{$('category').value='';form.elements.custom_category.value='일본 야담';}
  window.updateNewSettingSummary();notice('180분 · 15분씩 12장으로 설정했습니다. 제목과 이야기 방향을 입력해 주세요.');
};
storyChapterLabel.before(storyPreset);

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

document.querySelector('#new-form [name=parallax_mode]')?.addEventListener('change',window.updateNewSettingSummary);

// The overview shows stored evidence, never infers an image or render from a plan.
let productionPage=0, productionRevision=0;
const productionDetails=new Map();
const productionKey=job=>`${job.origin||'dedicated'}:${job.id}`;
function productionCell(text,kind='unknown',hint=''){
  const td=element('td'),badge=element('span',text,'production-badge '+kind);
  if(hint)badge.title=hint;td.append(badge);return td;
}
function productionMedia(info){
  if(!info||info.status==='unknown')return ['미확인','unknown'];
  const count=info.total?` ${info.count}/${info.total}`:'';
  return [{ready:'연결됨',partial:'일부 연결',running:'진행 중',failed:'실패',unverified:'파일 미확인',not_started:'미생성'}[info.status]||'미확인',info.status==='ready'?'ready':info.status==='running'?'running':'unknown',count];
}
function productionRow(job,detail){
  job={...job,...(detail?.job||{})};
  const row=element('tr'),title=element('td'),button=element('button',job.title||'제목 없음','production-title');
  button.onclick=async()=>{view('jobs');await showJob(job.id,job.origin||'dedicated');$('result').scrollIntoView({behavior:'smooth',block:'start'});};
  title.append(button,element('small',statusText(job.status)+' · '+displayLabel(job.stage||'')));row.append(title);
  if(!detail){for(let i=0;i<10;i++)row.append(productionCell('조회 중','running'));return row;}
  const d=detail.result_data||{},structure=d.structure||d.pregenerated_structure||{},scenes=Array.isArray(structure.scenes)?structure.scenes:[];
  const running=['queued','running'].includes(job.status),script=Boolean(detail.script),hasScene=fn=>scenes.some(fn);
  row.append(productionCell(script?'작성됨':running?'진행 중':'미확인',script?'ready':running?'running':'unknown'));
  const review=d.script_quality_report||d.listener_quality_report;
  row.append(productionCell(review?'결과 있음':running?'진행 중':'미확인',review?'ready':running?'running':'unknown','검수 결과의 존재 여부이며 합격 판정은 결과 상세에서 확인'));
  const chars=d.character_anchors||structure.character_anchors||d.main_character||structure.main_character;
  row.append(productionCell(chars?'설정됨':'미확인',chars?'ready':'unknown'));
  const directions=hasScene(s=>s.scene_direction_plan||s.ae_directorial_plan)||structure.scene_direction_plans?.length;
  row.append(productionCell(directions?'계획됨':'미확인',directions?'planned':'unknown','실제 AE 실행 완료가 아닌 연출 계획'));
  const bgm=d.bgm_plan||structure.bgm_plan||d.bgm_prompt||structure.bgm_prompt;
  row.append(productionCell(bgm?'계획 있음':'미확인',bgm?'planned':'unknown','음악 파일 생성 여부가 아닌 프롬프트·계획'));
  const sfx=d.sfx_plan||structure.sfx_plan||(Array.isArray(d.sfx_cues)&&d.sfx_cues.length?d.sfx_cues:null);
  row.append(productionCell(sfx?'계획 있음':'미확인',sfx?'planned':'unknown','효과음 파일 연결 여부와 별개'));
  const a=productionMedia(detail.media?.characters),b=productionMedia(detail.media?.images);
  row.append(productionCell(`인물 ${a[0]}${a[2]||''} · 장면 ${b[0]}${b[2]||''}`,a[1]==='ready'&&b[1]==='ready'?'ready':'unknown','저장된 이미지 링크 기준이며 파일 검증 결과는 아닙니다'));
  const layers=hasScene(s=>s.metadata?.psd_layer_asset?.qa_status==='approved'||s.metadata?.psd_layer_asset?.status==='ready');
  const layerPlans=hasScene(s=>s.psd_layer_plan?.enabled||s.parallax_plan?.enabled);
  row.append(productionCell(layers?'자료 있음':layerPlans?'계획됨':'미확인',layers?'ready':layerPlans?'planned':'unknown'));
  const coords=hasScene(s=>s.metadata?.cowork_image_asset?.speaker_geometry||s.metadata?.speaker_geometry);
  row.append(productionCell(coords?'기록 있음':'미확인',coords?'ready':'unknown'));
  row.append(productionCell('별도 확인','unknown','제출 후 통합워커의 AE·렌더 현황에서 확인'));
  return row;
}
async function loadProductionOverview(){
  const revision=++productionRevision;const tbody=$('production-rows');$('production-status').textContent='작업 결과를 확인하는 중…';
  try{
    const data=await api('history?'+new URLSearchParams({page:productionPage,origin:'all',state:'all',q:''}));
    const items=(data.items||[]).filter(j=>!['topics','script_plan_generate'].includes(j.mode||j.job_type));
    if(revision!==productionRevision)return;
    const rows=items.map(j=>productionRow(j,productionDetails.get(productionKey(j))));tbody.replaceChildren(...rows);
    $('production-page').textContent=`${productionPage+1} 페이지`; $('production-prev').disabled=productionPage===0; $('production-next').disabled=!data.has_more;
    let next=0,failed=0;
    await Promise.all(Array.from({length:Math.min(4,items.length)},async()=>{while(next<items.length){
      const index=next++,j=items[index];let detail=null;
      try{detail=await api(j.origin==='legacy'?'history/legacy/'+j.id:'jobs/'+j.id);productionDetails.set(productionKey(j),detail);}catch{failed++;detail=productionDetails.get(productionKey(j));}
      if(revision!==productionRevision)return;
      const replacement=productionRow(j,detail);if(!detail)for(const cell of replacement.querySelectorAll('td:not(:first-child) .production-badge')){cell.textContent='조회 실패';cell.className='production-badge unknown';}rows[index].replaceWith(replacement);rows[index]=replacement;
    }}));
    if(revision!==productionRevision)return;
    if(!items.length){const tr=element('tr'),td=element('td','이 페이지에 표시할 토픽 작업이 없습니다.');td.colSpan=11;tr.append(td);tbody.append(tr);}
    $('production-status').textContent=`이력 ${data.total??'—'}건 · 이 페이지 ${items.length}건 · 미확인은 저장된 결과만으로 확인할 수 없는 상태입니다.${failed?` · ${failed}건 조회 실패: 이전에 확인한 결과를 유지합니다.`:''}`;
    $('production-page').textContent=`${productionPage+1} 페이지`; $('production-prev').disabled=productionPage===0; $('production-next').disabled=!data.has_more;
  }catch(e){if(revision===productionRevision)$('production-status').textContent='작업 현황 조회 실패: '+e.message;}
}
$('production-prev').onclick=()=>{if(productionPage>0){productionPage--;void loadProductionOverview();}};
$('production-next').onclick=()=>{productionPage++;void loadProductionOverview();};
void loadProductionOverview();
setInterval(()=>{if(!$('view-overview').hidden)void loadProductionOverview();},15000);

let chatLoading=false;
async function loadChat(){if(chatLoading)return;chatLoading=true;try{const data=await api('chat');const box=$('chat-messages');box.replaceChildren();for(const m of data.messages||[]){const item=element('article',undefined,'chat-message '+m.role);item.append(element('strong',m.role==='user'?'나':'Codex'),element('p',m.text));box.append(item)}if(!data.messages?.length)box.append(element('p','무엇을 도와드릴까요?','muted'));const busyChat=['queued','running'].includes(data.state);$('chat-status').textContent=data.error||({queued:'대본워커의 앞선 작업이 끝나기를 기다리고 있습니다.',running:'Codex가 작업하고 있습니다.',interrupted:'이전 응답이 중단되었습니다.'}[data.state]||'');$('chat-send').disabled=busyChat;$('chat-new').disabled=busyChat;}catch(e){$('chat-status').textContent='채팅 연결 실패: '+e.message}finally{chatLoading=false}}
$('chat-form').onsubmit=async event=>{event.preventDefault();const input=$('chat-input'),message=input.value.trim();if(!message)return;$('chat-send').disabled=true;try{await api('chat',{message});input.value='';await loadChat();}catch(e){$('chat-status').textContent=e.message;$('chat-send').disabled=false}};
$('chat-new').onclick=async()=>{try{await api('chat/new',{});await loadChat()}catch(e){$('chat-status').textContent=e.message}};
setInterval(()=>{if(!$('view-chat').hidden)void loadChat()},2500);
