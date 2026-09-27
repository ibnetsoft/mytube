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
      for (const [key, name] of [['youtube_url', '유튜브 URL'], ['story', '스토리 개요'], ['character_notes', '캐릭터 설명'], ['requirements', '필수·금지 사항'], ['transcript', '직접 입력한 참고 자료']]) {
        if (!brief[key]) continue;
        const content = element('p', brief[key]); content.style.whiteSpace = 'pre-wrap';
        detail.append(element('h3', name), content);
      }
      detail.append(element('p', [brief.category, brief.duration_minutes + '분', brief.language, brief.setting_country, brief.era_region, brief.image_style, brief.production_mode].join(' · ')));
      const images = element('div'); images.style.cssText = 'display:flex;gap:12px;flex-wrap:wrap';
      for (const image of brief.character_images || []) {
        const figure = element('figure'), img = element('img'); img.src = image.data; img.alt = image.name;
        img.style.cssText = 'width:180px;height:180px;object-fit:contain'; figure.append(img, element('figcaption', image.name)); images.append(figure);
      }
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
    } catch (e) { error(e.message); }
  }
  button.onclick = () => { view('submissions'); load(); };
  window.loadWebTopics = load;
  reload.onclick = load; state.onchange = () => { detail.hidden = true; revision++; load(); };
  setInterval(() => { if (!section.hidden) load(); }, 15000);
})();
