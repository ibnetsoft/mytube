'use strict';
let historyPage=0,historyMore=false,historyRevision=0,historyLoading=false,resultSource=null;
const typeNames={new:'신규 대본',repair:'대본 리페어',grounded:'자료 기반',topics:'토픽 구성',script_generate:'대본 생성',script_plan_generate:'대본 기획',codex_content_generate:'콘텐츠 패키지',publish_metadata_generate:'메타데이터',sfx_plan_generate:'효과음 구성'};
function mediaThumbnail(media,title){
  const box=element('div',undefined,'history-thumbnail'),caption=element('span',media?.thumbnail?.label||'썸네일 미확인','thumbnail-caption');
  const url=media?.thumbnail?.url;
  if(url&&/^https:\/\//i.test(url)){
    const img=element('img');img.src=url;img.alt=(title||'대본')+' 썸네일';img.loading='lazy';img.referrerPolicy='no-referrer';
    img.onerror=()=>{img.remove();box.classList.add('thumbnail-empty');caption.textContent='썸네일 로드 실패';};
    box.append(img);
  }else{box.classList.add('thumbnail-empty');box.append(element('span','▧','thumbnail-placeholder'));}
  box.append(caption);return box;
}
function mediaBadges(media){
  const group=element('div',undefined,'media-badges');
  const names={ready:'생성됨',partial:'일부 생성',not_started:'미생성',running:'생성 중',failed:'실패',unknown:'미확인',unverified:'파일 미확인'};
  for(const [key,label] of [['characters','캐릭터'],['images','장면 이미지']]){
    const info=media?.[key]||{status:'unknown',count:0,total:0};
    const count=info.total?` ${info.count}/${info.total}`:info.count?` ${info.count}개`:'';
    const badge=element('span',`${label} · ${names[info.status]||'미확인'}${count}`,'media-badge');
    badge.dataset.status=info.status;badge.title=media?.basis||'미디어 기록 미확인';group.append(badge);
  }
  return group;
}
function historyRow(job){
  const row=element('div',undefined,'job'),info=element('div',undefined,'job-info');
  info.append(element('strong',job.title||'제목 없음'));
  const date=job.created_at?new Date(job.created_at*1000).toLocaleString('ko-KR'):'';
  info.append(element('small',`${job.origin==='legacy'?'기존 워커':'전용 워커'} · ${typeNames[job.job_type||job.mode]||job.job_type||job.mode} · ${date}`));
  info.append(element('small',`${labels[job.status]||job.status} · ${displayLabel(job.stage)}`));
  info.append(mediaBadges(job.media));
  if(job.media)info.append(element('small',job.media.basis,'media-basis'));
  if(job.sync_status==='pending')info.append(element('small','Database 저장 대기 · 로컬 복구본 보관 중','sync-warning'));
  const button=element('button','결과 보기');
  button.onclick=async()=>{await showJob(job.id,job.origin||'dedicated');if(selectedJob?.id===job.id)$('result').scrollIntoView({behavior:'smooth',block:'start'});};
  row.append(mediaThumbnail(job.media,job.title),info,button);return row;
}
async function loadHistory(){
  const revision=++historyRevision;historyLoading=true;
  const params=new URLSearchParams({page:historyPage,origin:$('history-origin').value,state:$('history-state').value,q:$('history-search').value});
  $('history-count').textContent='Database 이력 불러오는 중…';
  try{
    const data=await api('history?'+params);if(revision!==historyRevision)return;
    $('jobs').replaceChildren(...data.items.map(historyRow));
    if(!data.items.length)$('jobs').append(element('p','조회 조건에 맞는 작업이 없습니다.','muted'));
    $('history-count').textContent=`전체 ${(data.total??data.items.length).toLocaleString()}건 · Database 조회`;
    historyMore=data.has_more;$('history-page').textContent=`${historyPage+1} 페이지`;
    $('history-previous').disabled=historyPage===0;$('history-next').disabled=!historyMore;
  }catch(e){if(revision!==historyRevision)return;$('history-count').textContent='이력 조회 실패 · '+e.message;$('storage-status').textContent='Database 조회 실패';$('jobs').replaceChildren();$('history-next').disabled=true;}
  finally{if(revision===historyRevision)historyLoading=false;}
}
window.refreshManagement=async data=>{
  const pending=data.jobs.filter(j=>j.sync_status==='pending');
  $('storage-status').textContent=data.storage?.connected?'Database 연결됨':'Database 연결 확인 필요';
  $('storage-note').textContent=displayLabel(data.storage?.error)|| (pending.length?`${pending.length}개 작업 저장 대기 · 결과에서 재동기화`:'작업·결과·승인 기록 저장 / 로컬 복구본 유지');
  $('local-pending').hidden=!pending.length;
  $('local-pending').replaceChildren(element('h3','Database 저장 대기'),...pending.map(historyRow));
  if(!historyLoading)await loadHistory();
};
for(const id of ['history-origin','history-state'])$(id).onchange=()=>{historyPage=0;loadHistory();};
$('history-search-button').onclick=()=>{historyPage=0;loadHistory();};
$('history-search').onkeydown=e=>{if(e.key==='Enter')$('history-search-button').click();};
$('history-previous').onclick=()=>{if(historyPage>0){historyPage--;loadHistory();}};
$('history-next').onclick=()=>{if(historyMore){historyPage++;loadHistory();}};
window.renderManagementResult=(data,origin)=>{
  resultSource=data.source_link;
  $('result-origin').textContent=data.result_origin||'저장된 작업 결과';
  let mediaPanel=$('result-media');
  if(!mediaPanel){mediaPanel=element('div',undefined,'result-media');mediaPanel.id='result-media';$('result-origin').after(mediaPanel);}
  const info=element('div');info.append(mediaBadges(data.media),element('small',data.media?.basis||'미디어 기록 미확인'));
  mediaPanel.replaceChildren(mediaThumbnail(data.media,data.job.title),info);
  $('result-data').textContent=Object.keys(data.result_data||{}).length?JSON.stringify(data.result_data,null,2):'이 작업에 저장된 결과 데이터가 없습니다.';
  $('result-source').hidden=!resultSource;
  $('retry-job').hidden=origin==='legacy'||!['failed','interrupted'].includes(data.job.status);
  $('retry-job').disabled=busy;
  $('sync-job').hidden=origin==='legacy'||data.job.sync_status!=='pending';
};
$('result-source').onclick=async()=>{if(!resultSource)return;const item={...resultSource};view('repair');await readSource(item);};
$('sync-job').onclick=async()=>{if(!selectedJob)return;const id=selectedJob.id;$('sync-job').disabled=true;try{await api('jobs/'+id+'/sync',{});notice('Database에 요청·결과·승인 기록을 저장했습니다.');await showJob(id);await refresh();}catch(e){error(e.message);}finally{$('sync-job').disabled=false;}};
$('retry-job').onclick=async()=>{
  if(!selectedJob||busy||!confirm('같은 요청으로 새 작업을 실행할까요? AI 사용량이 발생하며 이전 실패 기록은 유지됩니다.'))return;
  $('retry-job').disabled=true;
  try{const job=await api('jobs/'+selectedJob.id+'/retry',{});await refresh();await showJob(job.id);notice('새 작업을 시작했습니다. 이전 작업과 연결해 기록합니다.');}catch(e){error(e.message);}finally{$('retry-job').disabled=busy;}
};
refresh();
