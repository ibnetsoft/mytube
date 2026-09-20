'use strict';
const topicPanel=element('article',undefined,'panel');
topicPanel.innerHTML=`<h2>선택한 소재로 토픽 자동 구성</h2><p>위 자료함에서 소재를 선택하면 원문 요약과 새 이야기 후보 3개를 만듭니다. 후보를 골라 신규 대본으로 이어갈 수 있습니다.</p><form id="topic-form"><div class="form-grid"><label>토픽 카테고리<input name="category" required maxlength="80" value="가족 사연" placeholder="가족 사연, 옛날이야기 등"></label><label>목표 분량 (분)<input name="duration_minutes" type="number" min="1" max="60" value="15" required></label></div><label>재구성 방향<textarea name="notes" maxlength="4000" rows="3" placeholder="살리고 싶은 감정, 바꿀 배경, 원하는 결말"></textarea></label><p class="muted">요약·분석: GPT-5.6 Sol · 토픽 창작: GPT-6 Astra. 원문 요약과 창작 후보를 구분해 저장하며 Codex 사용량이 발생합니다.</p><button id="topic-start" type="submit" class="primary">토픽 후보 3개 구성</button></form>`;
$('view-grounded').insertBefore(topicPanel,$('grounded-form').closest('article'));
$('topic-form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const source_ids=[...$('reference-list').querySelectorAll('input:checked')].map(input=>input.value);
  if(!source_ids.length){error('자막을 자료함에 저장한 뒤 사용할 자료를 선택하세요.');return;}
  const values=Object.fromEntries(new FormData(event.target));
  await start({...values,mode:'topics',source_ids,duration_minutes:Number(values.duration_minutes)});
};
const topicResults=element('div');$('result').append(topicResults);
window.renderTopicResult=data=>{
  topicResults.replaceChildren();
  if(data.job.mode!=='topics')return;
  const analysis=data.source_analysis;
  if(analysis){
    topicResults.append(element('h3','원문 분석'),element('p',analysis.summary),element('p','핵심 갈등: '+analysis.core_conflict));
    const turns=element('ul');analysis.turning_points.forEach(text=>turns.append(element('li',text)));topicResults.append(turns);
    if(analysis.uncertainties.length)topicResults.append(element('p','확인할 부분: '+analysis.uncertainties.join(' / '),'muted'));
    const evidence=element('details');evidence.append(element('summary','원문 근거 확인'));
    for(const item of analysis.evidence){const source=data.sources.find(s=>s.id===item.source_id);evidence.append(element('pre',(source?.title||item.source_id)+'\n'+(source?.locator||'')+'\n'+item.quote,'script'));}
    topicResults.append(evidence);
  }
  for(const [index,topic] of (data.topics||[]).entries()){
    const card=element('article',undefined,'panel');card.append(element('h3',(index+1)+'. '+topic.title),element('p','창작 토픽 · '+topic.premise));
    for(const [key,label] of [['protagonist','주인공'],['conflict','갈등'],['hook','도입'],['twist','반전'],['ending','결말'],['differentiation','원작과 차별점']])card.append(element('p',label+': '+topic[key]));
    const button=element('button','이 토픽으로 대본 준비','primary');button.type='button';
    button.onclick=()=>{
      const form=$('new-form'),draft=topic.generation_request;
      if((form.elements.title.value.trim()||form.elements.notes.value.trim())&&!confirm('신규 생성에 작성 중인 내용을 선택한 토픽으로 바꿀까요?'))return;
      form.elements.title.value=draft.title;form.elements.custom_category.value=draft.category;
      form.elements.duration.value=draft.duration_minutes;form.elements.notes.value=draft.notes;
      view('new');notice('선택한 토픽을 채웠습니다. 내용을 확인하고 대본 생성 시작을 누르세요.');
    };
    card.append(button);topicResults.append(card);
  }
};
