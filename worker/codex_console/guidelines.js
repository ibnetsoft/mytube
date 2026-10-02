'use strict';
(() => {
  titles.guidelines = '대본 지침 개선';
  const nav = element('button', '◎  대본 지침 개선'); nav.dataset.view = 'guidelines';
  document.querySelector('aside nav').append(nav);
  const section = element('section'); section.id = 'view-guidelines'; section.hidden = true;
  const panel = element('article', undefined, 'panel');
  panel.append(element('h2', '문제 기록 → 지침 승인 → 다음 대본에 적용'), element('p', 'Database가 기준 저장소입니다. 대기 중인 개선안은 적용되지 않습니다. 승인 후 같은 카테고리·언어의 새 작업부터 적용합니다.'));
  const form = element('form'), fields = {};
  for (const [key, text, max, multiline] of [['title','개선안 제목',200,false],['issue','발견한 문제·수정/반려 사유',4000,true],['instruction','다음 대본 작성·검수에 적용할 개선 지침',4000,true],['category','카테고리 (비우면 전체)',80,false],['source_job_id','관련 작업 ID (선택)',32,false]]) {
    const label = element('label', text), input = element(multiline ? 'textarea' : 'input'); input.maxLength = max;
    input.required = ['title','issue','instruction'].includes(key); label.append(input); form.append(label); fields[key] = input;
  }
  const language = element('select'), label = element('label', '대본 언어');
  for (const [value,text] of [['','전체'],['ko','한국어'],['ja','일본어'],['en','영어'],['es','스페인어'],['vi','베트남어'],['th','태국어']]) {
    const option = element('option',text); option.value = value; language.append(option);
  }
  label.append(language); form.append(label); fields.language = language;
  const submit = element('button','개선안 저장 · 승인 대기','primary'); submit.type = 'submit'; form.append(submit); panel.append(form);
  const list = element('article',undefined,'panel'), outcomes = element('article',undefined,'panel');
  section.append(panel,list,outcomes); document.querySelector('main').append(section);
  const statuses = {pending:'승인 대기',approved:'적용 중',rejected:'반려',retired:'비활성화'};
  async function load() {
    try {
      const data = await api('script-guidelines'); list.replaceChildren(element('h2','지침 버전·검토 이력'));
      if (!data.items.length) list.append(element('p','등록된 개선안이 없습니다.'));
      for (const row of data.items) {
        const card = element('article',undefined,'panel');
        card.append(element('h3',`v${row.version} · ${row.title} · ${statuses[row.status]}`),element('p',`카테고리: ${row.category || '전체'} / 언어: ${row.language || '전체'}`));
        for(const [name,text] of [['발견한 문제',row.issue],['개선 지침',row.instruction],['검토 의견',row.review_note || '없음']]) {
          const p = element('p',text); p.style.whiteSpace = 'pre-wrap'; card.append(element('strong',name),p);
        }
        if(row.source_job_id){const link=element('button','관련 대본 보기');link.onclick=async()=>{await showJob(row.source_job_id);view('jobs');};card.append(link);}
        const note = element('textarea'); note.placeholder = '검토 사유 (반려·비활성화 시 필수)'; note.maxLength=1000;
        const actions = row.status==='pending' ? [['approve','승인 · 다음 작업부터 적용'],['reject','반려']] : row.status==='approved' ? [['retire','비활성화']] : [];
        if(actions.length)card.append(note);
        for(const [action,text] of actions){const b=element('button',text);b.onclick=async()=>{b.disabled=true;try{await api(`script-guidelines/${row.id}/review`,{action,note:note.value});await load();}catch(e){error(e.message);}finally{b.disabled=false;}};card.append(b);}
        const mirror=element('button',row.notion_page_id?'Notion 복사 시점 스냅샷 저장됨':'Notion 열람용 복사 (선택)');mirror.disabled=Boolean(row.notion_page_id) || row.status!=='approved';
        mirror.onclick=async()=>{mirror.disabled=true;try{await api(`script-guidelines/${row.id}/notion-sync`,{});await load();}catch(e){error(e.message);mirror.disabled=false;}};
        card.append(mirror);list.append(card);
      }
      outcomes.replaceChildren(element('h2','적용 결과 · 최근 대본 검수'));
      outcomes.append(element('p','검수 점수는 자동 검수 결과입니다. 사용자 확인과 함께 지침 효과를 판단하세요.'));
      for(const row of data.outcomes){const d=element('details');d.append(element('summary',`${row.title} · ${statusText(row.status)} · 적용: ${(row.applied_versions || []).map(v=>'v'+v.version).join(', ') || '없음'}`));d.append(element('pre',JSON.stringify(row.evaluation,null,2)));outcomes.append(d);}
      if(!data.outcomes.length)outcomes.append(element('p','아직 기록된 검수 결과가 없습니다. 다음 대본 작업부터 기록됩니다.'));
    }catch(e){error(e.message);}
  }
  form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{await api('script-guidelines',Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value])));form.reset();await load();notice('개선안을 저장했습니다. 승인 전에는 적용되지 않습니다.');}catch(e){error(e.message);}finally{submit.disabled=false;}};
  nav.onclick=()=>{view('guidelines');load();};
})();
