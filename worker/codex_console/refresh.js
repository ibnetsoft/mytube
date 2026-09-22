'use strict';
const refreshStateKey='codex-script-console-refresh-v1';
function refreshFieldKey(field){
  if(field.id)return {id:field.id};
  if(field.form?.id&&field.name)return {form:field.form.id,name:field.name};
  return null;
}
function captureRefreshState(){
  const fields=[];
  for(const field of document.querySelectorAll('input,textarea,select')){
    if(['file','password','hidden'].includes(field.type))continue;
    const key=refreshFieldKey(field);if(!key)continue;
    fields.push({...key,value:field.value,checked:field.checked});
  }
  return {savedAt:Date.now(),view:document.querySelector('main>section:not([hidden])')?.id.replace('view-','')||'overview',
    fields,catalogPage:page,historyPage,source:currentSource?{kind:currentSource.kind,id:currentSource.id}:null,
    job:selectedJob?{id:selectedJob.id,origin:selectedJob.origin}:null,
    references:[...document.querySelectorAll('#reference-list input:checked')].map(x=>x.value),
    scrollY:window.scrollY,newCountryOverridden:window.newCountryOverridden,
    topicCountryOverridden:typeof topicCountryOverridden==='boolean'?topicCountryOverridden:false};
}
$('refresh').onclick=async()=>{
  const button=$('refresh');if(button.disabled)return;
  button.disabled=true;button.textContent='새로 불러오는 중…';button.setAttribute('aria-busy','true');
  try{
    // Browsers cannot restore a selected File after navigation.
    if([...document.querySelectorAll('input[type=file]')].some(f=>f.files?.length)){
      await refresh();
      if(!$('view-repair').hidden)await loadCatalog();
      if(selectedJob&&!$('view-jobs').hidden)await showJob(selectedJob.id,selectedJob.origin);
      notice('선택한 파일을 유지하기 위해 데이터만 갱신했습니다.');
      button.disabled=false;button.textContent='새로고침 ↻';button.removeAttribute('aria-busy');return;
    }
    sessionStorage.setItem(refreshStateKey,JSON.stringify(captureRefreshState()));
    window.location.reload();
  }catch(e){
    error('입력값을 보관하지 못해 새로고침을 중단했습니다. '+e.message);
    button.disabled=false;button.textContent='새로고침 ↻';button.removeAttribute('aria-busy');
  }
};
document.addEventListener('DOMContentLoaded',async()=>{
  let saved;
  try{const raw=sessionStorage.getItem(refreshStateKey);sessionStorage.removeItem(refreshStateKey);if(raw)saved=JSON.parse(raw);}catch{return;}
  if(!saved||Date.now()-saved.savedAt>30*60*1000)return;
  notice('페이지를 새로 불러왔습니다. 메뉴와 입력값을 복원하는 중…');
  await window.categoriesReady;
  for(const entry of saved.fields||[]){
    const field=entry.id?$(entry.id):$(entry.form)?.elements.namedItem(entry.name);
    if(!field||['file','password','hidden'].includes(field.type))continue;
    // A removed category must not silently choose another category on reload.
    if(field.tagName==='SELECT'&&![...field.options].some(o=>o.value===entry.value)){
      const option=element('option',entry.value||'직접 입력');option.value=entry.value;field.append(option);
    }
    field.value=entry.value;
    if(['checkbox','radio'].includes(field.type))field.checked=Boolean(entry.checked);
  }
  window.newCountryOverridden=Boolean(saved.newCountryOverridden);
  if(typeof topicCountryOverridden==='boolean')topicCountryOverridden=Boolean(saved.topicCountryOverridden);
  for(const prefix of ['new','topic']){
    const country=$(prefix+'-country'),custom=$(prefix+'-custom-country');
    if(country&&custom)custom.style.display=country.value==='custom'?'block':'none';
  }
  window.updateNewSettingSummary?.();
  if(typeof updateTopicSettingSummary==='function')updateTopicSettingSummary();
  page=Math.max(0,Number(saved.catalogPage)||0);historyPage=Math.max(0,Number(saved.historyPage)||0);
  const name=['overview','new','repair','jobs','grounded'].includes(saved.view)?saved.view:'overview';
  view(name);
  try{
    if(name==='jobs'){
      await loadHistory();
      if(saved.job)await showJob(saved.job.id,saved.job.origin||'dedicated');
    }else if(name==='repair'&&saved.source){await readSource(saved.source);}
    else if(name==='grounded'){
      await loadReferences();
      const selected=new Set(saved.references||[]);
      document.querySelectorAll('#reference-list input').forEach(f=>{f.checked=selected.has(f.value);});
    }
    notice('페이지를 새로 불러왔습니다 · '+new Date().toLocaleTimeString('ko-KR'));
    window.scrollTo({top:saved.scrollY||0,behavior:'instant'});
  }catch(e){error('페이지는 새로 불러왔지만 일부 데이터를 복원하지 못했습니다. '+e.message);}
});
