'use strict';
// These are the real form controls, including controls added by later scripts.
window.scriptSettingsQuestions=[
 ['어떤 방식의 대본을 만들까요?',['production_mode','script_style']],
 ['어떤 주제와 자료를 사용할까요?',['title','category','custom_category','youtube_url']],
 ['얼마나 긴 이야기로 만들까요?',['duration','chapter_minutes']],
 ['어떤 언어와 배경으로 만들까요?',['language','setting_country','custom_country','era_region']],
 ['어떤 그림과 연출을 사용할까요?',['image_style','direction_profile']],
 ['영상 씬과 분리 레이어는 어떻게 준비할까요?',['parallax_mode','required_video_scene_count','image_layer_mode','image_layer_scene_start','image_layer_scene_end']],
 ['같은 구도의 장면 상태 변화가 필요할까요?',['character_state_count','character_state_scene_start','character_state_scene_end']],
 ['배경음악 프롬프트와 추가 요청이 있나요?',['generate_bgm_prompt','notes']],
];
window.reviewScriptSettings=function(form,canStart=()=>true){
 if(form.dataset.settingsReview==='open')return Promise.resolve(false);
 form.dataset.settingsReview='open';
 return new Promise(resolve=>{
  const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const dialog=make('dialog');dialog.className='script-settings-review';dialog.setAttribute('aria-labelledby','settings-review-title');
  const progress=make('p'),heading=make('h2'),body=make('div'),message=make('p'),nav=make('div');
  heading.id='settings-review-title';body.className='settings-review-fields';message.setAttribute('role','alert');
  const cancel=make('button','취소'),back=make('button','이전'),next=make('button','이 설정으로 다음');
  for(const b of [cancel,back,next])b.type='button';next.className='primary';nav.className='settings-review-actions';nav.append(cancel,back,next);
  dialog.append(progress,heading,body,message,nav);document.body.append(dialog);
  const questions=window.scriptSettingsQuestions.map(([title,names])=>[title,names.filter(name=>form.elements.namedItem(name))]).filter(([,names])=>names.length);
  let step=0,finished=false;
  const field=name=>form.elements.namedItem(name);
  const label=c=>{const l=c.closest('label');return l?[...l.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim():c.name;};
  const readable=c=>c.type==='checkbox'?(c.checked?'사용':'사용 안 함'):c.tagName==='SELECT'?(c.selectedOptions[0]?.textContent||'선택 안 함'):(c.value||'입력 안 함');
  const availability=setInterval(()=>{if(step===questions.length){next.disabled=!canStart();message.textContent=canStart()?'':'현재 대본 작업이 끝난 뒤 시작할 수 있습니다. 설정은 먼저 확인할 수 있습니다.';}},1000);
  function finish(confirmed){if(finished)return;finished=true;clearInterval(availability);delete form.dataset.settingsReview;dialog.close();dialog.remove();resolve(confirmed);}
  function render(){
   body.replaceChildren();message.textContent='';progress.textContent=`대본 생성 전 설정 확인 · ${step+1}/${questions.length+1}`;
   back.disabled=step===0;next.disabled=false;
   if(step===questions.length){
    heading.textContent='이 설정으로 대본 생성을 시작할까요?';
    if(field('production_mode')?.value==='standard' && field('parallax_mode')?.value==='selective' && field('image_layer_mode')?.value==='hybrid' && field('image_layer_scene_start')?.value && field('image_layer_scene_end')?.value && Number(field('character_state_count')?.value||0)===0){
     body.append(make('p',`선택 범위 ${field('image_layer_scene_start').value}~${field('image_layer_scene_end').value}씬은 분리 레이어와 입모양·패럴럭스 등 AE 연출을 준비합니다. 범위 밖은 씬당 이미지 1장입니다. 범위 이후에는 문맥에 맞는 줌·좌우 이동과 씬 전환을 사용하며 느린 줌은 사용하지 않습니다.`));
    }
    for(const [title,names] of questions){const section=make('section');section.append(make('h3',title));const list=make('dl');
     for(const name of names){const c=field(name);if(c.type==='hidden'||(name==='custom_country'&&field('setting_country')?.value!=='custom'))continue;list.append(make('dt',label(c)),make('dd',readable(c)));}section.append(list);body.append(section);}
    next.textContent='확인한 설정으로 대본 생성 시작';next.disabled=!canStart();if(!canStart())message.textContent='현재 대본 작업이 끝난 뒤 시작할 수 있습니다. 설정은 먼저 확인할 수 있습니다.';return;
   }
   const [title,names]=questions[step];heading.textContent=title;next.textContent='이 설정으로 다음';
   for(const name of names){
    const original=field(name);if(name==='custom_country'&&field('setting_country')?.value!=='custom')continue;
    const wrapper=make('label',label(original)),copy=original.cloneNode(true);copy.removeAttribute('id');copy.removeAttribute('name');copy.disabled=false;copy.style.display='';
    copy.dataset.setting=name;copy.value=original.value;if(original.type==='checkbox')copy.checked=original.checked;
    const sync=()=>{if(original.type==='checkbox')original.checked=copy.checked;else original.value=copy.value;original.dispatchEvent(new Event('input',{bubbles:true}));original.dispatchEvent(new Event('change',{bubbles:true}));};
    copy.addEventListener('input',()=>{if(copy.tagName!=='SELECT')sync();});copy.addEventListener('change',()=>{sync();if(copy.tagName==='SELECT')render();});
    wrapper.append(copy);const help=original.closest('label')?.querySelector('small');if(help)wrapper.append(help.cloneNode(true));body.append(wrapper);
   }
  }
  cancel.onclick=()=>finish(false);dialog.addEventListener('cancel',e=>{e.preventDefault();finish(false);});back.onclick=()=>{step--;render();};
  next.onclick=()=>{
   for(const c of body.querySelectorAll('input,select,textarea'))if(!c.reportValidity())return;
   if(step<questions.length){
    const names=questions[step][1];
    for(const [start,end,required] of [['image_layer_scene_start','image_layer_scene_end',false],['character_state_scene_start','character_state_scene_end',Number(field('character_state_count')?.value)>0]]){
     if(!names.includes(start))continue;
     const a=field(start)?.value,b=field(end)?.value;
     if((required||a||b)&&(!a||!b||Number(a)>Number(b))){message.textContent='시작·종료 씬을 모두 입력하고, 종료 씬을 시작 씬 이상으로 지정해 주세요.';return;}
    }
   }
   if(step===questions.length){
    const invalid=[...form.elements].find(c=>c.willValidate&&!c.checkValidity());
    if(invalid){const index=questions.findIndex(([,names])=>names.includes(invalid.name));if(index>=0){step=index;render();message.textContent='입력 내용을 확인해 주세요.';}return;}
    finish(true);
   }else{step++;render();dialog.scrollTop=0;}
  };
  render();dialog.showModal();
 });
};
