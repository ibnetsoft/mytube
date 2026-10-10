'use strict';
(() => {
  titles.submissions = '웹 토픽 승인';
  const nav = document.querySelector('aside nav');
  const button = element('button', '▤  웹 토픽 승인'); button.dataset.view = 'submissions';
  nav.append(button);
  const section = element('section'); section.id = 'view-submissions'; section.hidden = true;
  const panel = element('article', undefined, 'panel');
  panel.append(element('h2', '사용자 등록 토픽'), element('p', '내용을 확인하고 승인하면 대본 작성을 시작합니다. 승인 전에는 실행되지 않습니다.'));
  const toolbar = element('div', undefined, 'toolbar'), state = element('select');
  for (const [value, text] of [['pending', '승인 대기'], ['approved', '승인됨'], ['rejected', '반려']]) {
    const option = element('option', text); option.value = value; state.append(option);
  }
  const reload = element('button', '새로고침'), list = element('div'), detail = element('article', undefined, 'panel');
  detail.hidden = true; toolbar.append(state, reload); panel.append(toolbar, list); section.append(panel, detail);
  document.querySelector('main').append(section);
  let loading = false, reviewing = false, revision = 0;
  async function load() {
    if (loading) return; loading = true;
    try {
      const data = await api('web-topics?state=' + state.value); list.replaceChildren();
      if (!data.items.length) list.append(element('p', '등록된 토픽이 없습니다.', 'muted'));
      for (const item of data.items) {
        const row = element('div', undefined, 'toolbar');
        row.append(element('strong', item.title), element('span', item.owner_email + ' · ' + new Date(item.created_at).toLocaleString(), 'muted'));
        const open = element('button', '내용 보기'); open.onclick = () => show(item.id); row.append(open);
        if (item.job_id) {
          const result = element('button', '작업 상태 · 결과');
          result.onclick = async () => { try { await showJob(item.job_id); view('jobs'); } catch (e) { error(e.message); } };
          row.append(result);
        }
        list.append(row);
      }
    } catch (e) { error(e.message); }
    finally { loading = false; }
  }
  async function show(id) {
    const current = ++revision; detail.hidden = true;
    try {
      const row = await api('web-topics/' + id); if (current !== revision) return;
      const brief = row.request_data; detail.replaceChildren(element('h2', row.title), element('p', row.owner_email));
      const translatedNodes = {title: detail.querySelector('h2')};
      const translationStatus = element('p', '한국어 번역 중… (로컬 Codex)', 'muted');
      detail.append(translationStatus);
      const original = element('details'); original.append(element('summary', '원문 보기'), element('h3', row.title));
      const languages = {ko:'한국어',ja:'일본어',en:'영어',es:'스페인어',vi:'베트남어',th:'태국어'};
      const styles = {realistic:'실사',cinematic:'시네마틱',anime:'애니메이션',ghibli:'지브리',webtoon:'웹툰',korean_webtoon:'한국 웹툰','3d':'3D',minimal:'미니멀',wimpy:'윔피'};
      const settings = element('dl', undefined, 'topic-review-settings');
      const field = (name, value) => {
        const cell = element('div'), content = element('dd', value == null || value === '' ? '미입력' : String(value));
        cell.append(element('dt', name), content); settings.append(cell); return content;
      };
      field('등록자', row.owner_email);
      field('등록 일시', row.created_at ? new Date(row.created_at).toLocaleString('ko-KR') : '미입력');
      field('승인 상태', {pending:'승인 대기',approved:'승인됨',rejected:'반려'}[row.status] || row.status);
      field('카테고리', brief.category);
      field('분량', brief.duration_minutes == null ? '' : brief.duration_minutes + '분');
      field('입력 언어', languages[brief.input_language] || brief.input_language);
      field('대본 언어', languages[brief.language] || brief.language);
      translatedNodes.setting_country = field('배경 국가', brief.setting_country);
      translatedNodes.era_region = field('시대·지역', brief.era_region);
      field('이미지 스타일', styles[brief.image_style] || brief.image_style);
      field('제작 모드', {standard:'기존 영상',moving_comic:'무빙툰'}[brief.production_mode] || brief.production_mode);
      field('AE 씬 영상 전달 방식', {gcs:'GCS 업로드',local:'로컬 전달'}[brief.ae_scene_delivery] || brief.ae_scene_delivery);
      if (row.reviewed_at) field('검토 일시', new Date(row.reviewed_at).toLocaleString('ko-KR'));
      if (row.job_id) field('대본 작업 ID', row.job_id);
      detail.append(element('h3', '등록 설정'), settings);
      for (const key of ['category','duration_minutes','input_language','language','setting_country','era_region','image_style','production_mode','ae_scene_delivery']) {
        original.append(element('p', key + ': ' + (brief[key] ?? '미입력')));
      }
      for (const [key, name] of [['youtube_url', '유튜브 URL'], ['story', '스토리 개요'], ['character_notes', '캐릭터 설명'], ['requirements', '필수·금지 사항'], ['transcript', '직접 입력한 참고 자료']]) {
        const content = element('p', brief[key] || '미입력'); content.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere';
        detail.append(element('h3', name), content);
        if (key !== 'youtube_url') translatedNodes[key] = content;
        const source = element('p', brief[key] || '미입력'); source.style.whiteSpace = 'pre-wrap';
        original.append(element('h3', name), source);
      }
      detail.append(original);
      detail.append(element('h3', '첨부한 캐릭터 이미지 (' + (brief.character_images || []).length + '장)'));
      const images = element('div'); images.style.cssText = 'display:flex;gap:12px;flex-wrap:wrap';
      for (const image of brief.character_images || []) {
        const figure = element('figure'), img = element('img'); img.src = image.data; img.alt = image.name;
        figure.style.cssText = 'margin:0 0 20px;max-width:100%;overflow-wrap:anywhere';
        img.style.cssText = 'width:180px;height:180px;object-fit:contain';
        const expanded = element('details'), full = element('img'); full.src = image.data; full.alt = image.name;
        full.style.cssText = 'display:block;max-width:100%;height:auto;margin-top:12px';
        expanded.append(element('summary', '원본 크기로 보기'), full);
        figure.append(img, element('figcaption', image.name), expanded); images.append(figure);
      }
      if (!(brief.character_images || []).length) images.append(element('p', '첨부 없음', 'muted'));
      detail.append(images);
      if (row.status === 'pending') {
        const label = element('label', '검토 의견 (반려 시 필수)'), note = element('textarea'); note.maxLength = 1000; label.append(note);
        const approve = element('button', '승인 · 대본 작성 시작', 'primary'), reject = element('button', '반려');
        async function review(action) {
          if (reviewing) return;
          if (action === 'reject' && !note.value.trim()) { error('반려 사유를 입력하세요.'); note.focus(); return; }
          reviewing = true; approve.disabled = reject.disabled = true; error('');
          try {
            const result = await api('web-topics/' + id + '/review', { action, note: note.value });
            detail.hidden = true; await load();
            notice(action === 'approve' ? '승인한 토픽으로 대본 작성을 시작했습니다.' : '토픽을 반려했습니다.');
            if (action === 'approve') { view('jobs'); await showJob(result.id); await refresh(); }
          } catch (e) { error(e.message); await load(); }
          finally { reviewing = false; approve.disabled = reject.disabled = false; }
        }
        approve.onclick = () => review('approve'); reject.onclick = () => review('reject');
        detail.append(label, approve, reject);
      } else { detail.append(element('p', '검토 의견: ' + (row.review_note || '없음'))); }
      detail.hidden = false;
      async function translate() {
        try {
          const result = await api('web-topics/' + id + '/korean-review', {});
          if (current !== revision || detail.hidden) return;
          if (result.status === 'running') { setTimeout(translate, 2000); return; }
          if (result.status !== 'completed') throw new Error(result.error || '한국어 번역 실패');
          for (const [key, node] of Object.entries(translatedNodes)) node.textContent = result.translation[key] || (key === 'title' ? row.title : brief[key]) || '미입력';
          translationStatus.textContent = '한국어 번역 · 원문은 변경하지 않았습니다.';
        } catch (e) {
          if (current !== revision) return;
          translationStatus.textContent = e.message;
          const retry = element('button', '번역 다시 시도'); retry.onclick = () => { retry.remove(); translate(); }; translationStatus.append(retry);
        }
      }
      translate();
    } catch (e) { error(e.message); }
  }
  button.onclick = () => { view('submissions'); load(); };
  window.loadWebTopics = load;
  reload.onclick = load; state.onchange = () => { detail.hidden = true; revision++; load(); };
  setInterval(() => { if (!section.hidden) load(); }, 15000);
})();
