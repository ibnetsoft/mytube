'use strict';
(() => {
 const names=['대본','이미지 프롬프트','영상 씬·프롬프트','AE 지침'];
 const states={pending:'시작 대기',running:'생성 중',review:'검토 대기',approved:'확정',stale:'이전 단계 변경 · 다시 생성',failed:'실행 실패 · 재시도 가능'};
 const intro=element('p','새 대본은 ① 대본 → ② 이미지 프롬프트 → ③ 영상 씬·프롬프트 → ④ AE 지침 순서로 진행합니다. 각 결과를 수정·확정한 뒤 다음 단계를 직접 시작하세요.','callout');
 $('new-form').prepend(intro);
 function syncManualControls(){
  const manual=!$('production-mode')||$('production-mode').value!=='nonverbal_preschool';intro.hidden=!manual;
  for(const name of ['required_video_scene_count','generate_publish_package','generate_bgm_prompt']){
   const field=$('new-form').elements.namedItem(name);if(field){field.disabled=manual;field.closest('label').hidden=manual;}
  }
 }
 $('production-mode')?.addEventListener('change',syncManualControls);syncManualControls();
 window.renderManualStages=(data,origin)=>{
  const root=$('manual-stages'),w=data.result_data?.manual_workflow;
  root.hidden=!w;
  if(!w){root.replaceChildren();delete root.dataset.job;delete root.dataset.hash;return;}
  $('approve').hidden=true;$('retry-job').hidden=true;
  const key=data.job.id+':'+data.job.candidate_hash;
  if(root.dataset.key===key)return;
  if(root.dataset.job===data.job.id&&root.dataset.dirty==='true'){
   if(!root.querySelector('[data-stale-warning]')){const warning=element('div','결과 버전이 변경됐습니다. 입력을 보존하고 있습니다. ');warning.dataset.staleWarning='true';const reload=element('button','입력 버리고 최신 결과 보기');reload.onclick=()=>{root.dataset.dirty='false';delete root.dataset.key;window.renderManualStages(data,origin)};warning.append(reload);root.prepend(warning)}return;
  }
  if(root.dataset.job!==data.job.id)root.dataset.active=String(Math.max(0,w.stages.findIndex(s=>s.status!=='approved')));
  root.dataset.job=data.job.id;root.dataset.key=key;root.dataset.dirty='false';root.replaceChildren();
  root.append(element('h3','단계별 수동 진행'),element('p','확정과 다음 단계 시작은 별도입니다. 결과는 저장되며, 자동으로 다음 단계나 이미지·영상 제작을 실행하지 않습니다.','muted'));
  const nav=element('div',undefined,'toolbar');root.append(nav);
  w.stages.forEach((s,i)=>{const b=element('button',`${i+1}. ${names[i]} · ${states[s.status]||s.status}`);b.setAttribute('aria-pressed',String(i===Number(root.dataset.active)));b.onclick=()=>{if(root.dataset.dirty==='true'){notice('수정 내용을 먼저 저장하거나 버려 주세요.');return;}root.dataset.active=String(i);delete root.dataset.key;window.renderManualStages(data,origin)};nav.append(b)});
  const index=Number(root.dataset.active)||0,step=w.stages[index],draft=structuredClone(step.output||{}),locked=w.stages.slice(0,index).some(s=>s.status!=='approved'),running=['queued','running'].includes(data.job.status);
  root.append(element('h3',`${index+1}/4 ${names[index]} · ${states[step.status]}`));
  if(locked)root.append(element('p','앞 단계를 확정하면 이 단계를 시작할 수 있습니다.','callout'));
  const controls=element('div',undefined,'toolbar'),form=element('div'),feedback=element('textarea'),save=element('button','수정 저장'),approve=element('button','이 단계 확정'),generate=element('button',step.output?'이 단계 다시 생성':`${names[index]} 생성 시작`),discard=element('button','수정 버리기');
  const dirty=()=>{root.dataset.dirty='true';save.disabled=running;approve.disabled=true;generate.disabled=true;discard.disabled=false;};
  function field(parent,label,value,onChange,short=false){const wrap=element('label',label),input=element(short?'input':'textarea');input.value=value||'';input.setAttribute('aria-label',label);if(!short)input.rows=Math.min(12,Math.max(3,String(value||'').split('\n').length+1));input.disabled=running||locked||step.status==='stale';input.oninput=()=>{onChange(input.value);dirty()};wrap.append(input);parent.append(wrap);}
  if(step.output){
   const rows=draft[['scenes','cuts','selections','directions'][index]];
   rows.forEach((row,n)=>{
    const article=element('article',undefined,'panel');form.append(article);article.append(element('h4',index===0?`씬 ${n+1}`:row.cut_id));
    if(index===0){field(article,`씬 ${n+1} 제목`,row.title,v=>row.title=v,true);field(article,`씬 ${n+1} 화면 상황 · 낭독 제외`,row.visual_action,v=>row.visual_action=v);row.spoken_blocks.forEach((b,j)=>{if(b.kind==='dialogue')field(article,`씬 ${n+1} 대사 ${j+1} 화자`,b.speaker,v=>b.speaker=v,true);field(article,`씬 ${n+1} ${b.kind==='narration'?'나레이션':'대사'} ${j+1}`,b.text,v=>b.text=v)});if(!row.spoken_blocks.length)article.append(element('p','무음 장면'));}
    if(index===1){article.append(element('p','연결 씬: '+row.scene_id));field(article,row.cut_id+' 이미지 프롬프트',row.image_prompt,v=>row.image_prompt=v);field(article,row.cut_id+' 필요한 참조 자산 · 한 줄에 하나',row.references.join('\n'),v=>row.references=v.split('\n').map(s=>s.trim()).filter(Boolean));}
    if(index===2){const label=element('label','영상으로 만들 컷 선택 '),check=element('input');check.type='checkbox';check.checked=row.selected;check.disabled=running||locked||step.status==='stale';check.setAttribute('aria-label',row.cut_id+' 영상 선택');check.onchange=()=>{row.selected=check.checked;dirty()};label.prepend(check);article.append(label);field(article,row.cut_id+' 선택 이유',row.reason,v=>row.reason=v);field(article,row.cut_id+' 영상 프롬프트',row.video_prompt,v=>row.video_prompt=v);}
    if(index===3){field(article,row.cut_id+' AE 지침',row.ae_instruction,v=>row.ae_instruction=v);field(article,row.cut_id+' 적용 시점·읽기 구간',row.timing_note,v=>row.timing_note=v);}
   });
   if(draft.review)form.append(element('p',draft.review.status==='user_edited'?'사용자 수정본 · 이전 자동 검토는 수정 전 버전에 한정됩니다.':draft.review.passed?'이 단계 계획 검토 통과':'이 단계 검토 의견을 확인해 주세요.','callout'));
   if(draft.quality_notes.length){const note=element('details');note.append(element('summary','검토 메모'),element('pre',draft.quality_notes.map(v=>typeof v==='string'?v:JSON.stringify(v)).join('\n'),'script'));form.append(note)}
  }
  feedback.placeholder='이 단계 재생성에 반영할 수정 요청';feedback.setAttribute('aria-label','단계 수정 요청');feedback.rows=3;feedback.disabled=running||locked;
  root.append(form,feedback,controls);
  const action=async(kind)=>{[save,approve,generate,discard].forEach(b=>b.disabled=true);try{await api('jobs/'+data.job.id+'/manual-stage',{action:kind,step:index+1,expected_hash:data.job.candidate_hash,...(kind==='save'?{output:draft}:{}),feedback:feedback.value});root.dataset.dirty='false';delete root.dataset.key;await showJob(data.job.id,origin);void refresh();notice(kind==='approve'?'이 단계를 확정했습니다. 다음 단계는 직접 시작해 주세요.':kind==='save'?'수정 내용을 저장했습니다.':'선택한 단계의 생성을 시작했습니다.');}catch(e){error(e.message);save.disabled=root.dataset.dirty!=='true';generate.disabled=running||locked||root.dataset.dirty==='true';approve.disabled=running||locked||root.dataset.dirty==='true'||!['review','approved'].includes(step.status);}};
  save.disabled=true;approve.disabled=running||locked||!['review','approved'].includes(step.status);generate.disabled=running||locked;discard.disabled=true;
  save.onclick=()=>void action('save');approve.onclick=()=>void action('approve');generate.onclick=()=>void action('generate');discard.onclick=()=>{root.dataset.dirty='false';delete root.dataset.key;window.renderManualStages(data,origin)};
  controls.append(save,discard,approve,generate);
  if(step.status==='approved'&&index<3){const next=element('button','다음 단계 열기');next.onclick=()=>{if(root.dataset.dirty==='true')return;root.dataset.active=String(index+1);delete root.dataset.key;window.renderManualStages(data,origin)};controls.append(next)}
  if(w.stages.every(s=>s.status==='approved'))root.append(element('p','4단계 결과를 모두 확정했습니다. 대본과 제작 지침이 저장됐습니다.','callout'));
 };
 if(typeof view==='function'){
  const match=location.hash.match(/^#manual=([a-f0-9]{32})$/);
  if(match){view('jobs');void showJob(match[1],'dedicated');}
  else if(location.hash==='#jobs')view('jobs');
  else if(location.hash==='#new')view('new');
 }
})();
