'use strict';
(() => {
  titles.settings = '대본 설정';
  const nav = element('button', '⚙  대본 설정'); nav.dataset.view = 'settings';
  nav.onclick = () => view('settings'); document.querySelector('aside nav').append(nav);
  const section = element('section'); section.id = 'view-settings'; section.hidden = true;
  const panel = element('article', undefined, 'panel');
  panel.append(element('h2', '새 대본 기본 설정'), element('p', '이 대본워커에서 생성할 대본의 기본값입니다. 대본 작성·번역은 이 컴퓨터의 Codex CLI로 실행합니다. 저장한 기본값은 다음 신규 생성에 사용하며, 기존 대본과 진행 중 작업은 바꾸지 않습니다.'));
  const form = element('form'), grid = element('div', undefined, 'form-grid'), fields = {};
  grid.style.gridTemplateColumns = 'repeat(auto-fit,minmax(min(240px,100%),1fr))';
  const entries = [
    ['category','카테고리'], ['production_mode','제작 모드'], ['script_style','대본 스타일'],
    ['duration_minutes','분량 (분)','duration'], ['language','대본 언어'], ['setting_country','배경 국가'],
    ['era_region','시대·지역'], ['image_style','이미지 스타일'], ['image_layer_mode','이미지 레이어'],
    ['direction_profile','연출 프로필'], ['parallax_mode','패럴럭스 제작'], ['image_layer_scene_start','레이어 시작 씬 (선택)'],
    ['image_layer_scene_end','레이어 종료 씬 (선택)'], ['required_video_scene_count','필수 영상 씬 수'],
    ['generate_bgm_prompt','배경음악 프롬프트 생성'], ['notes','기본 작성 방향']
  ];
  for (const [name,text,sourceName] of entries) {
    const source = document.querySelector(`#new-form [name="${sourceName || name}"]`);
    const control = source ? source.cloneNode(true) : element('input');
    control.removeAttribute('id'); control.name = name; control.disabled = false;
    control.querySelectorAll('[id]').forEach(node=>node.removeAttribute('id'));
    if (name==='setting_country') { control.querySelector('option[value=custom]')?.remove(); }
    if (name==='duration_minutes') control.max = '60';
    const label = element('label',text); label.append(control);
    if(name==='notes')label.style.gridColumn='1 / -1';
    grid.append(label); fields[name] = control;
  }
  const save = element('button','대본 기본값 저장','primary'); save.type='submit';
  const apply = element('button','저장한 기본값을 신규 생성에 적용'); apply.type='button';
  const status=element('p',undefined,'muted'); status.setAttribute('role','status');
  form.append(grid,save,apply,status); panel.append(form); section.append(panel); document.querySelector('main').append(section);
  let defaults=null, saving=false; const touched=new Set();
  $('new-form').addEventListener('input',event=>touched.add(event.target.name));
  $('new-form').addEventListener('change',event=>touched.add(event.target.name));
  function fill(settings) {
    for(const [name,control] of Object.entries(fields)) {
      if(control.type==='checkbox')control.checked=Boolean(settings[name]);else control.value=settings[name]??'';
    }
  }
  function applyDefaults(force=false) {
    if(!defaults)return;
    for(const [name,,sourceName] of entries) {
      const target=$('new-form').elements[sourceName||name];
      if(!target||(!force&&touched.has(target.name)))continue;
      if(target.type==='checkbox')target.checked=Boolean(defaults[name]);else target.value=defaults[name]??'';
    }
    window.updateNewSettingSummary();
  }
  form.onsubmit=async event=>{
    event.preventDefault();if(saving)return;saving=true;save.disabled=true;status.textContent='저장 중…';
    try{
      const value={};
      for(const [name,control] of Object.entries(fields))value[name]=control.type==='checkbox'?control.checked:control.type==='number'?(control.value===''?null:Number(control.value)):control.value;
      if(value.duration_minutes===null)throw Error('분량을 입력하세요.');
      if(value.required_video_scene_count===null)throw Error('필수 영상 씬 수를 입력하세요.');
      if(fields.category.selectedOptions?.[0]?.dataset.id)value.category_id=fields.category.selectedOptions[0].dataset.id;
      defaults=(await api('script-settings',value)).settings;fill(defaults);status.textContent='대본 기본값 저장 완료 · 다음 신규 생성부터 적용';
    }catch(e){status.textContent=e.message;error(e.message)}finally{saving=false;save.disabled=false}
  };
  apply.onclick=()=>{applyDefaults(true);view('new');notice('저장한 대본 기본값을 적용했습니다. 생성 전에 확인하세요.');};
  save.disabled=true;apply.disabled=true;
  Promise.resolve(window.categoriesReady).then(async()=>{
    const source=$('new-form').elements.category;fields.category.replaceChildren(...Array.from(source.options).map(o=>o.cloneNode(true)));
    defaults=(await api('script-settings')).settings;fill(defaults);applyDefaults();save.disabled=false;apply.disabled=false;
  }).catch(e=>{status.textContent=e.message;error(e.message)});
})();
