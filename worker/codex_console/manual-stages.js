'use strict';
(() => {
 const names=['대본','이미지 프롬프트','영상 씬·프롬프트','AE 지침','효과음 프롬프트'];
 const states={pending:'시작 대기',running:'생성 중',review:'검토 대기',approved:'확정',stale:'이전 단계 변경 · 다시 생성',failed:'실행 실패 · 재시도 가능'};
 const intro=element('p','새 대본은 ① 대본 → ② 이미지 프롬프트 → ③ 영상 씬·프롬프트 → ④ AE 지침 → ⑤ 효과음 프롬프트 순서로 진행합니다. 각 결과를 수정·확정한 뒤 다음 단계를 직접 시작하세요.','callout');
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
  if(root.dataset.job===data.job.id&&(root.dataset.dirty==='true'||root.dataset.sceneDirty==='true')){
   if(!root.querySelector('[data-stale-warning]')){const warning=element('div','결과 버전이 변경됐습니다. 입력을 보존하고 있습니다. ');warning.dataset.staleWarning='true';const reload=element('button','입력 버리고 최신 결과 보기');reload.onclick=()=>{root.dataset.dirty='false';root.dataset.sceneDirty='false';delete root.dataset.key;window.renderManualStages(data,origin)};warning.append(reload);root.prepend(warning)}return;
  }
  if(root.dataset.job!==data.job.id)root.dataset.active=String(Math.max(0,w.stages.findIndex(s=>s.status!=='approved')));
  root.dataset.job=data.job.id;root.dataset.key=key;root.dataset.dirty='false';root.replaceChildren();
  root.append(element('h3','단계별 수동 진행'),element('p','확정과 다음 단계 시작은 별도입니다. 결과는 저장되며, 자동으로 다음 단계나 이미지·영상 제작을 실행하지 않습니다.','muted'));
  const policyPanel=element('section',undefined,'panel');root.append(policyPanel);
  policyPanel.append(element('h4','실행 지침 · 생성 전 준비와 원화 검수'),element('p','지침 확인은 그림 검수 통과가 아닙니다. 실제 원화·고정 자산·좌우·적의 동작 상태를 확인해야 합니다.','muted'));
  const policyInfo=element('div');policyPanel.append(policyInfo);
  const updateDetails=element('details');updateDetails.append(element('summary','발견한 개선점을 다음 작업 지침에 추가'));
  const ruleTitle=element('input'),ruleReason=element('textarea'),ruleText=element('textarea'),ruleSave=element('button','개선 지침 저장·적용');
  ruleTitle.placeholder='개선 항목 이름';ruleTitle.setAttribute('aria-label','개선 항목 이름');ruleReason.placeholder='실제로 발견한 문제와 근거';ruleReason.setAttribute('aria-label','개선 근거');ruleText.placeholder='다음 생성·검수에서 확인할 구체적인 기준';ruleText.setAttribute('aria-label','개선 지침');updateDetails.append(ruleTitle,ruleReason,ruleText,ruleSave);policyPanel.append(updateDetails);
  let currentPolicy;
  const loadPolicy=async()=>{currentPolicy=await api('wuxia-generation-policy');policyInfo.replaceChildren(element('p',`기본 ${currentPolicy.revision}판 · 추가 개선 ${currentPolicy.update_revision||0}회 · 확인 항목 ${currentPolicy.rules.length}개`));currentPolicy.rules.forEach(rule=>policyInfo.append(element('p','• '+rule.title)));root.querySelectorAll('[data-reviewed-policy]').forEach(figure=>figure.hidden=figure.dataset.reviewedPolicy!==currentPolicy.sha256);root.querySelectorAll('[data-guidance-sha]').forEach(label=>label.textContent=label.dataset.guidanceSha===currentPolicy.sha256?'최신 지침을 입력에 반영한 프롬프트 · 실제 그림 검수는 별도':'최신 개선 지침으로 프롬프트·생성 준비 재검토 필요');};
  ruleSave.onclick=async()=>{if(root.dataset.dirty==='true'||root.dataset.sceneDirty==='true'){notice('입력 중인 내용을 먼저 저장해 주세요.');return;}ruleSave.disabled=true;try{await api('wuxia-generation-policy',{expected_hash:currentPolicy.sha256,rule_id:'correction_'+Date.now(),title:ruleTitle.value,instruction:ruleText.value,reason:ruleReason.value});await loadPolicy();notice('개선 지침을 저장했습니다. 다음 생성 입력부터 반영되며 기존 그림은 재검토가 필요합니다.');}catch(e){error(e.message);}finally{ruleSave.disabled=false;}};
  void loadPolicy().catch(e=>error(e.message));
  if(w.stages.length===4)w.stages.push({name:names[4],status:'pending'});
  const nav=element('div',undefined,'toolbar');root.append(nav);
  w.stages.forEach((s,i)=>{const b=element('button',`${i+1}. ${names[i]} · ${states[s.status]||s.status}`);b.setAttribute('aria-pressed',String(i===Number(root.dataset.active)));b.onclick=()=>{if(root.dataset.dirty==='true'||root.dataset.sceneDirty==='true'){notice('수정 내용을 먼저 저장하거나 버려 주세요.');return;}root.dataset.active=String(i);delete root.dataset.key;window.renderManualStages(data,origin)};nav.append(b)});
  const index=Number(root.dataset.active)||0,step=w.stages[index],draft=structuredClone(step.output||{}),locked=w.stages.slice(0,index).some(s=>s.status!=='approved'),running=['queued','running'].includes(data.job.status);
  root.append(element('h3',`${index+1}/5 ${names[index]} · ${states[step.status]}`));
  if(locked)root.append(element('p','앞 단계를 확정하면 이 단계를 시작할 수 있습니다.','callout'));
  const controls=element('div',undefined,'toolbar'),form=element('div'),feedback=element('textarea'),save=element('button','수정 저장'),approve=element('button','이 단계 확정'),generate=element('button',step.output?'이 단계 다시 생성':`${names[index]} 생성 시작`),discard=element('button','수정 버리기');
  const dirty=()=>{root.dataset.dirty='true';root.querySelectorAll('section.panel input,section.panel textarea,section.panel button').forEach(control=>control.disabled=true);save.disabled=running;approve.disabled=true;generate.disabled=true;discard.disabled=false;};
  function field(parent,label,value,onChange,short=false){const wrap=element('label',label),input=element(short?'input':'textarea');input.value=value||'';input.setAttribute('aria-label',label);if(!short)input.rows=Math.min(12,Math.max(3,String(value||'').split('\n').length+1));input.disabled=running||locked||step.status==='stale';input.oninput=()=>{onChange(input.value);dirty()};wrap.append(input);parent.append(wrap);}
  if(step.output){
   const rows=draft[['scenes','cuts','selections','directions','cues'][index]];
   rows.forEach((row,n)=>{
    const article=element('article',undefined,'panel');form.append(article);article.append(element('h4',index===0?`씬 ${n+1}`:row.cut_id));
    if(index===0){field(article,`씬 ${n+1} 제목`,row.title,v=>row.title=v,true);field(article,`씬 ${n+1} 화면 상황 · 낭독 제외`,row.visual_action,v=>row.visual_action=v);row.spoken_blocks.forEach((b,j)=>{if(b.kind==='dialogue')field(article,`씬 ${n+1} 대사 ${j+1} 화자`,b.speaker,v=>b.speaker=v,true);field(article,`씬 ${n+1} ${b.kind==='narration'?'나레이션':'대사'} ${j+1}`,b.text,v=>b.text=v)});if(!row.spoken_blocks.length)article.append(element('p','무음 장면'));
     const entry=w.scene_image_prompts?.[row.scene_id]||{},box=element('section',undefined,'panel');article.append(box);
     box.append(element('h4','이 씬의 이미지 프롬프트'),element('p','1화 공용 참조를 선택하고 이 씬만 생성하세요. 실제 이미지 제작은 실행하지 않습니다.','muted'));
     const status=element('p',entry.status==='stale'?'대본 변경 · 프롬프트 재검토 필요':entry.status==='running'?'이 씬 프롬프트 생성 중':entry.status==='failed'?entry.error:entry.image_prompt?'프롬프트 검토 대기':'프롬프트 추가 가능');box.append(status);
     const guidance=element('p','최신 지침 대조 중…','callout');guidance.dataset.guidanceSha=entry.guidance_applied?.policy_sha256||'';box.append(guidance);
     const quality=w.quality_control?.[row.scene_id]||{},qDetails=element('details');qDetails.append(element('summary','생성 전 입력 점검·발견한 문제 기록'));
     if(quality.image_use_status)qDetails.append(element('p',quality.image_use_status==='reviewed'?'원화 검수 기록 있음 · 최신 지침과 파일 일치 재확인 필요':'현재 후보 원화 사용 제외 · 수정 후 실제 그림 재검수 필요','callout'));
     const ruleSelect=element('select'),findingText=element('textarea'),recordFinding=element('button','이 씬의 문제 기록'),checkInput=element('button','실제 이미지 생성 입력 점검'),qResult=element('div');
     ruleSelect.setAttribute('aria-label',`씬 ${n+1} 문제 종류`);findingText.setAttribute('aria-label',`씬 ${n+1} 문제 근거`);findingText.placeholder='어느 인물·부위·컷에서 무엇이 다른지';
     qDetails.ontoggle=()=>{if(qDetails.open&&currentPolicy&&!ruleSelect.options.length)currentPolicy.rules.forEach(r=>{const option=element('option',r.title);option.value=r.id;ruleSelect.append(option)});};
     qDetails.append(ruleSelect,findingText,recordFinding,checkInput,qResult);box.append(qDetails);
     for(const candidate of quality.candidates||[]){if(candidate.use_status!=='reviewed'||!candidate.asset?.cut_id)continue;const figure=element('figure'),image=element('img');figure.hidden=true;figure.dataset.reviewedPolicy=candidate.review?.policy_sha256||'';image.src='api/jobs/'+data.job.id+'/assets/file/'+encodeURIComponent(candidate.asset.cut_id)+'?local_token='+encodeURIComponent(token);image.alt=candidate.asset.cut_id+' 검토 원화';image.loading='lazy';image.style.cssText='width:100%;height:auto;display:block';figure.append(element('figcaption',candidate.asset.cut_id+' · 실제 원화 검수본 / 사용자 확인 대기'),image);box.append(figure);}

     (quality.findings||[]).filter(f=>f.status==='open').forEach(f=>qResult.append(element('p','미해결: '+f.evidence)));
     const qualityAction=async(action,payload={})=>{if(root.dataset.dirty==='true'||root.dataset.sceneDirty==='true'){notice('입력 중인 내용을 먼저 저장해 주세요.');return;}try{const result=await api('jobs/'+data.job.id+'/scene-quality',{action,scene_id:row.scene_id,expected_hash:data.job.candidate_hash,data:payload});if(action==='preflight'){qResult.replaceChildren(element('p',result.ready?'생성 입력 준비 확인 · 실제 그림 검수는 별도':'실제 이미지 생성 전 준비가 필요합니다.'),...result.issues.map(v=>element('p','• '+v)));return;}delete root.dataset.key;await showJob(data.job.id,origin);}catch(e){error(e.message);}};
     recordFinding.onclick=()=>void qualityAction('finding',{rule_id:ruleSelect.value,evidence:findingText.value});checkInput.onclick=()=>void qualityAction('preflight');
     const refs=element('details'),summary=element('summary','1화 인물·소품·장면 이미지 공유'),gallery=element('div',undefined,'scene-reference-gallery');refs.append(summary,gallery);box.append(refs);
     const chosen=new Set((entry.references||[]).map(r=>r.id)),selected=element('p');box.append(selected);
     const prompt=element('textarea');prompt.value=entry.image_prompt||'';prompt.rows=6;prompt.setAttribute('aria-label',`씬 ${n+1} 이미지 프롬프트`);prompt.disabled=running;box.append(prompt);
     const note=element('textarea');note.placeholder='이 씬의 구도·동작·참조 사용 요청';note.value=entry.feedback||'';note.rows=2;note.setAttribute('aria-label',`씬 ${n+1} 이미지 요청`);note.disabled=running;box.append(note);
     const toolbar=element('div',undefined,'toolbar'),saveScene=element('button','이 씬 프롬프트 저장'),generateScene=element('button',entry.image_prompt?'이 씬 프롬프트 다시 생성':'이 씬 이미지 프롬프트 생성');toolbar.append(saveScene,generateScene);box.append(toolbar);
     let sceneDirty=false;const changed=()=>{sceneDirty=true;root.dataset.sceneDirty='true';root.querySelectorAll('section.panel').forEach(other=>{if(other!==box)other.querySelectorAll('input,textarea,button').forEach(control=>control.disabled=true);});root.querySelectorAll('input,textarea').forEach(control=>{if(!box.contains(control))control.disabled=true;});};prompt.oninput=changed;note.oninput=changed;
     const updateSelected=()=>{selected.textContent='연결 참조: '+((window.manualReferenceImages||[]).filter(r=>chosen.has(r.id)).map(r=>r.label).join(' / ')||'선택 없음');};
     const loadRefs=async()=>{try{if(!window.manualReferenceImages)window.manualReferenceImages=(await api('manual-reference-images')).images;gallery.replaceChildren();for(const r of window.manualReferenceImages){const label=element('label',undefined,'scene-reference-item'),check=element('input'),img=element('img');check.type='checkbox';check.checked=chosen.has(r.id);check.disabled=running;check.setAttribute('aria-label',`씬 ${n+1} 참조 ${r.label}`);check.onchange=()=>{check.checked?chosen.add(r.id):chosen.delete(r.id);changed();updateSelected();};img.src=r.url;img.alt=r.label;img.loading='lazy';img.style.cssText='width:110px;height:75px;object-fit:contain;display:block';label.append(check,img,element('span',r.label));gallery.append(label);}updateSelected();}catch(e){error(e.message);}};
     refs.ontoggle=()=>{if(refs.open&&!gallery.childElementCount)void loadRefs();};
     selected.textContent='연결 참조: '+((entry.references||[]).map(r=>r.label).join(' / ')||'선택 없음');
     const sceneAction=async(action)=>{if(root.dataset.dirty==='true'){notice('대본 수정 내용을 먼저 저장해 주세요.');return;}saveScene.disabled=generateScene.disabled=true;try{await api('jobs/'+data.job.id+'/scene-image-prompt',{action,scene_id:row.scene_id,expected_hash:data.job.candidate_hash,reference_ids:[...chosen],image_prompt:prompt.value,feedback:note.value});sceneDirty=false;root.dataset.sceneDirty='false';delete root.dataset.key;await showJob(data.job.id,origin);void refresh();notice(action==='save'?'이 씬의 프롬프트와 참조를 저장했습니다.':'이 씬의 이미지 프롬프트 생성을 시작했습니다.');}catch(e){error(e.message);saveScene.disabled=generateScene.disabled=running;}};
     saveScene.disabled=generateScene.disabled=running;saveScene.onclick=()=>void sceneAction('save');generateScene.onclick=()=>void sceneAction('generate');
    }
    if(index===1){article.append(element('p','연결 씬: '+row.scene_id));field(article,row.cut_id+' 이미지 프롬프트',row.image_prompt,v=>row.image_prompt=v);field(article,row.cut_id+' 필요한 참조 자산 · 한 줄에 하나',row.references.join('\n'),v=>row.references=v.split('\n').map(s=>s.trim()).filter(Boolean));}
    if(index===2){const label=element('label','영상으로 만들 컷 선택 '),check=element('input');check.type='checkbox';check.checked=row.selected;check.disabled=running||locked||step.status==='stale';check.setAttribute('aria-label',row.cut_id+' 영상 선택');check.onchange=()=>{row.selected=check.checked;dirty()};label.prepend(check);article.append(label);field(article,row.cut_id+' 선택 이유',row.reason,v=>row.reason=v);field(article,row.cut_id+' 영상 프롬프트',row.video_prompt,v=>row.video_prompt=v);}
    if(index===3){field(article,row.cut_id+' AE 지침',row.ae_instruction,v=>row.ae_instruction=v);field(article,row.cut_id+' 적용 시점·읽기 구간',row.timing_note,v=>row.timing_note=v);}
    if(index===4){field(article,row.cut_id+' 효과음 ID',row.id,v=>row.id=v,true);field(article,row.cut_id+' ElevenLabs 영문 프롬프트',row.prompt,v=>row.prompt=v);for(const [key,label] of [['duration_seconds','생성 길이(초)'],['offset_seconds','씬 시작 후 위치(초)'],['volume_db','음량(dB)']])field(article,row.cut_id+' '+label,String(row[key]),v=>row[key]=Number(v),true);field(article,row.cut_id+' 실제 사건·선택 이유',row.reason,v=>row.reason=v);article.append(element('p','소리 생성은 사용자 제출 후 통합워커에서 실행합니다. 지금은 프롬프트만 저장합니다.'));}

   });
   if(draft.review)form.append(element('p',draft.review.status==='user_edited'?'사용자 수정본 · 이전 자동 검토는 수정 전 버전에 한정됩니다.':draft.review.passed?'이 단계 계획 검토 통과':'이 단계 검토 의견을 확인해 주세요.','callout'));
   if(draft.quality_notes.length){const note=element('details');note.append(element('summary','검토 메모'),element('pre',draft.quality_notes.map(v=>typeof v==='string'?v:JSON.stringify(v)).join('\n'),'script'));form.append(note)}
  }
  feedback.placeholder='이 단계 재생성에 반영할 수정 요청';feedback.setAttribute('aria-label','단계 수정 요청');feedback.rows=3;feedback.disabled=running||locked;
  root.append(form,feedback,controls);
  const action=async(kind)=>{if(root.dataset.sceneDirty==='true'){notice('씬 이미지 프롬프트의 수정 내용을 먼저 저장해 주세요.');return;}[save,approve,generate,discard].forEach(b=>b.disabled=true);try{await api('jobs/'+data.job.id+'/manual-stage',{action:kind,step:index+1,expected_hash:data.job.candidate_hash,...(kind==='save'?{output:draft}:{}),feedback:feedback.value});root.dataset.dirty='false';delete root.dataset.key;await showJob(data.job.id,origin);void refresh();notice(kind==='approve'?'이 단계를 확정했습니다. 다음 단계는 직접 시작해 주세요.':kind==='save'?'수정 내용을 저장했습니다.':'선택한 단계의 생성을 시작했습니다.');}catch(e){error(e.message);save.disabled=root.dataset.dirty!=='true';generate.disabled=running||locked||root.dataset.dirty==='true';approve.disabled=running||locked||root.dataset.dirty==='true'||!['review','approved'].includes(step.status);}};
  save.disabled=true;approve.disabled=running||locked||!['review','approved'].includes(step.status);generate.disabled=running||locked;discard.disabled=true;
  save.onclick=()=>void action('save');approve.onclick=()=>void action('approve');generate.onclick=()=>void action('generate');discard.onclick=()=>{root.dataset.dirty='false';root.dataset.sceneDirty='false';delete root.dataset.key;window.renderManualStages(data,origin)};
  controls.append(save,discard,approve,generate);
  if(step.status==='approved'&&index<3){const next=element('button','다음 단계 열기');next.onclick=()=>{if(root.dataset.dirty==='true'||root.dataset.sceneDirty==='true')return;root.dataset.active=String(index+1);delete root.dataset.key;window.renderManualStages(data,origin)};controls.append(next)}
  if(w.stages.every(s=>s.status==='approved'))root.append(element('p','5단계 결과를 모두 확정했습니다. 대본과 제작 지침이 저장됐습니다.','callout'));
 };
 if(typeof view==='function'){
  const match=location.hash.match(/^#manual=([a-f0-9]{32})$/);
  if(match){view('jobs');void showJob(match[1],'dedicated');}
  else if(location.hash==='#jobs')view('jobs');
  else if(location.hash==='#new')view('new');
 }
})();
