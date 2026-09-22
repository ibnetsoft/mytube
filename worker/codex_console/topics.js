'use strict';
const topicPanel=element('article',undefined,'panel');
topicPanel.innerHTML=`<h2>선택한 소재로 토픽 자동 구성</h2><p>위 자료함에서 소재를 선택하면 원문 요약과 새 이야기 후보 3개를 만듭니다. 후보를 골라 신규 대본으로 이어갈 수 있습니다.</p>
<form id="topic-form">
  <div class="form-grid">
    <label>토픽 카테고리<input name="category" required maxlength="80" value="가족 사연" placeholder="가족 사연, 옛날이야기 등"></label>
    <label>목표 분량 (분)<input name="duration_minutes" type="number" min="1" max="60" value="15" required></label>
  </div>
  <div class="form-grid" style="grid-template-columns:1fr 1fr 1fr 1fr">
    <label>대본 언어
      <select name="language" id="topic-language">
        <option value="ko">한국어</option>
        <option value="en">영어</option>
        <option value="ja">일본어</option>
        <option value="es">스페인어</option>
      </select>
    </label>
    <label>배경 국가
      <select name="setting_country" id="topic-country">
        <option value="한국">한국</option>
        <option value="미국">미국</option>
        <option value="일본">일본</option>
        <option value="스페인">스페인</option>
        <option value="영국">영국</option>
        <option value="멕시코">멕시코</option>
        <option value="custom">직접 입력…</option>
      </select>
      <input name="custom_country" id="topic-custom-country" placeholder="직접 국가 입력" style="display:none;margin-top:6px" maxlength="40">
    </label>
    <label>시대·지역
      <input name="era_region" id="topic-era" value="현대 지방 소도시" maxlength="100" placeholder="현대 지방 소도시">
    </label>
    <label>이미지 스타일
      <select name="image_style" id="topic-style">
        <option value="실사">실사</option>
        <option value="시네마틱">시네마틱</option>
        <option value="애니메이션">애니메이션</option>
        <option value="일러스트">일러스트</option>
        <option value="웹툰">웹툰</option>
      </select>
    </label>
  </div>
  <div class="setting-preview">최종 설정: <strong id="topic-setting-summary">한국어 · 한국 현대 지방 소도시 · 실사</strong></div>
  <label>재구성 방향<textarea name="notes" maxlength="4000" rows="3" placeholder="살리고 싶은 감정, 바꿀 배경, 원하는 결말"></textarea></label>
  <p class="muted">요약·분석: GPT-5.6 Sol · 토픽 창작: GPT-6 Astra. 원문 요약과 창작 후보를 구분해 저장하며 AI 사용량이 발생합니다.</p>
  <button id="topic-start" type="submit" class="primary">토픽 후보 3개 구성</button>
</form>`;
$('view-grounded').insertBefore(topicPanel,$('grounded-form').closest('article'));
let topicCountryOverridden = false;
function updateTopicSettingSummary() {
  const form = $('topic-form');
  if (!form) return {};
  const lang = form.elements.language?.value || 'ko';
  const countrySelect = $('topic-country');
  const customCountry = $('topic-custom-country');
  let country = countrySelect.value === 'custom' ? (customCountry.value.trim() || '직접 입력') : countrySelect.value;
  const era = form.elements.era_region?.value.trim() || '현대 지방 소도시';
  const style = form.elements.image_style?.value || '실사';
  const summary = `${langNames[lang] || lang} · ${country} ${era} · ${style}`;
  const el = $('topic-setting-summary');
  if (el) el.textContent = summary;
  return { language: lang, setting_country: country, era_region: era, image_style: style, summary_label: summary };
}
if ($('topic-language')) {
  $('topic-language').onchange = e => {
    const lang = e.target.value;
    if (!topicCountryOverridden) {
      const def = defaultCountryByLanguage[lang] || '한국';
      $('topic-country').value = def;
      $('topic-custom-country').style.display = 'none';
    }
    updateTopicSettingSummary();
  };
  $('topic-country').onchange = e => {
    topicCountryOverridden = true;
    const isCustom = e.target.value === 'custom';
    $('topic-custom-country').style.display = isCustom ? 'block' : 'none';
    if (isCustom) $('topic-custom-country').focus();
    updateTopicSettingSummary();
  };
  $('topic-custom-country').oninput = updateTopicSettingSummary;
  $('topic-era').oninput = updateTopicSettingSummary;
  $('topic-style').onchange = updateTopicSettingSummary;
  updateTopicSettingSummary();
}
$('topic-form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const source_ids=[...$('reference-list').querySelectorAll('input:checked')].map(input=>input.value);
  if(!source_ids.length){error('자막을 자료함에 저장한 뒤 사용할 자료를 선택하세요.');return;}
  const setting = updateTopicSettingSummary();
  const form = event.target;
  await start({
    mode:'topics',
    source_ids,
    category: form.elements.category.value.trim(),
    duration_minutes: Number(form.elements.duration_minutes.value),
    notes: form.elements.notes.value,
    language: setting.language,
    setting_country: setting.setting_country,
    era_region: setting.era_region,
    image_style: setting.image_style,
  });
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
      form.elements.title.value=draft.title;
      form.elements.custom_category.value=draft.category;
      form.elements.language.value=draft.language||'ko';
      const countrySelect = $('new-country');
      const country = draft.setting_country || '한국';
      if ([...countrySelect.options].some(o => o.value === country)) {
        countrySelect.value = country;
        $('new-custom-country').style.display = 'none';
      } else {
        countrySelect.value = 'custom';
        $('new-custom-country').value = country;
        $('new-custom-country').style.display = 'block';
      }
      window.newCountryOverridden = true;
      if (form.elements.era_region) form.elements.era_region.value = draft.era_region || '현대 지방 소도시';
      if (form.elements.image_style) form.elements.image_style.value = draft.image_style || '실사';
      form.elements.duration.value=draft.duration_minutes;
      form.elements.notes.value=draft.notes;
      if (window.updateNewSettingSummary) window.updateNewSettingSummary();
      view('new');notice('선택한 토픽과 배경 설정을 채웠습니다. 내용을 확인하고 대본 생성 시작을 누르세요.');
    };
    card.append(button);topicResults.append(card);
  }
};
