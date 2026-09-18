'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="local-token"]').content;
let page = 0, hasMore = false, currentSource = null, selectedJob = null, busy = false, catalogRevision = 0;
const titles = {overview:'Codex 대본 워커',new:'신규 콘텐츠 생성',repair:'기존 대본 리페어',jobs:'작업 이력 · 결과',doc:'작업 지침'};
const labels = {queued:'대기',running:'실행 중',failed:'실패',interrupted:'중단 · 재시작 필요',awaiting_approval:'검토 대기',approved_pending_repair:'승인 · 적용 대기'};
function error(message) { $('error').textContent = message || ''; $('error').hidden = !message; }
function notice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
async function api(path, body) {
  const response = await fetch('/api/'+path,{headers:{'X-Codex-Local':token,'Content-Type':'application/json'},...(body?{method:'POST',body:JSON.stringify(body)}:{})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string'?data.detail: data.error || '요청 실패');
  return data;
}
function element(tag,text,className) { const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(className)node.className=className; return node; }
function view(name) {
  document.querySelectorAll('main>section').forEach(s=>s.hidden=s.id!=='view-'+name);
  document.querySelectorAll('nav [data-view]').forEach(b=>b.classList.toggle('selected',b.dataset.view===name));
  $('heading').textContent=titles[name];
  if(name==='repair')loadCatalog();
  if(name==='jobs')refresh();
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
document.querySelectorAll('[data-doc]').forEach(b=>b.addEventListener('click',async()=>{try{const data=await api('docs/'+b.dataset.doc);$('document').textContent=data.text;view('doc');}catch(e){error(e.message);}}));
async function refresh(){try{
  const data=await api('status'); error('');
  $('cli').textContent=data.codex_installed?'CLI 설치 확인':'CLI 없음'; $('cli-note').textContent=data.login_status;
  $('job-count').textContent=data.jobs.length; $('approval-count').textContent=data.jobs.filter(j=>j.status==='awaiting_approval').length;
  $('output').textContent='패키지 저장 위치: '+data.output;
  busy=data.jobs.some(j=>['running','queued'].includes(j.status));
  document.querySelector('#new-form button[type=submit]').disabled=busy; $('repair-start').disabled=busy||!currentSource;
  const container=$('jobs');container.replaceChildren();
  data.jobs.forEach(job=>{const row=element('div',undefined,'job');const info=element('div',undefined,'job-info');info.append(element('strong',job.title),element('small',(job.mode==='repair'?'리페어':job.mode==='grounded'?'자료 기반':'신규')+' · '+(labels[job.status]||job.status)+' · '+job.stage));row.append(info);const button=element('button','결과 보기');button.onclick=()=>showJob(job.id);row.append(button);container.append(row);});
  if(!data.jobs.length)container.append(element('p','아직 이 콘솔에서 실행한 작업이 없습니다. 기존 토픽은 리페어 목록에서 조회하세요.'));
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
$('refresh').onclick=()=>{refresh();if(!$('view-repair').hidden)loadCatalog();};
async function start(body){if(busy)return;busy=true;error('');try{const result=await api('jobs',body);notice('로컬 작업을 시작했습니다. 기존 운영 대본은 변경하지 않습니다.');view('jobs');await showJob(result.id);}catch(e){error(e.message);}finally{await refresh();}}
$('new-form').onsubmit=e=>{e.preventDefault();const form=new FormData(e.target);const category=form.get('custom_category').trim()||form.get('category');if(!category){error('카테고리를 입력하세요.');return;}if(!confirm('Codex 신규 대본 생성기를 실행할까요? CLI 사용량이 발생하며 결과는 로컬에 저장합니다.'))return;start({mode:'new',title:form.get('title'),category,category_id:form.get('custom_category').trim()?'':$('category').selectedOptions[0].dataset.id||'',duration_minutes:Number(form.get('duration')),generate_bgm_prompt:form.get('generate_bgm_prompt')==='on',notes:form.get('notes')});};
$('repair-start').onclick=()=>{if(!currentSource||busy)return;if(!confirm('이 대본의 Astra 수정안을 생성할까요? 원본은 보존하고 결과를 로컬에 저장합니다.'))return;start({mode:'repair',kind:currentSource.kind,source_id:currentSource.id,notes:$('repair-notes').value});};
async function showJob(id){try{const data=await api('jobs/'+id);selectedJob=data.job;$('result').hidden=false;$('result-title').textContent=data.job.title;$('result-status').textContent=(labels[data.job.status]||data.job.status)+' · '+data.job.stage+(data.job.error?' · '+data.job.error:'');$('original').textContent=data.original||'신규 생성 — 원본 없음';$('candidate').textContent=data.script||'아직 저장된 결과가 없습니다.';$('remaining').replaceChildren(...data.remaining.map(text=>element('li',text)));$('approve').hidden=data.job.status!=='awaiting_approval';if(window.renderGroundedResult)window.renderGroundedResult(data);}catch(e){error(e.message);}}
$('approve').onclick=async()=>{if(!selectedJob||!confirm('표시된 대본 버전에 승인 기록을 남길까요? 운영 대본 적용은 실행하지 않습니다.'))return;try{await api('jobs/'+selectedJob.id+'/approve',{candidate_hash:selectedJob.candidate_hash});notice('승인 기록을 저장했습니다. 연관 자료 검증과 운영 적용은 남아 있습니다.');await showJob(selectedJob.id);refresh();}catch(e){error(e.message);}};
api('categories').then(data=>{const options=data.items.map(c=>{const o=element('option',c.name);o.value=c.name;o.dataset.id=c.id;return o;});const custom=element('option','직접 입력');custom.value='';$('category').replaceChildren(...options,custom);}).catch(e=>error(e.message));
refresh();setInterval(()=>{if(document.hidden)return;refresh();if(selectedJob&&!$('view-jobs').hidden)showJob(selectedJob.id);},10000);
