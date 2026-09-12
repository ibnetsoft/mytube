(() => {
  const host = document.createElement('div');
  host.id = 'air-gemini-narrator';
  host.style.cssText = 'position:fixed;right:24px;bottom:24px;z-index:2147483647';
  const root = host.attachShadow({mode: 'open'});
  root.innerHTML = `
    <style>
      *{box-sizing:border-box}section{width:370px;padding:22px;background:#17202d;color:#eff5ff;border:1px solid #364253;border-radius:18px;box-shadow:0 12px 45px #0005;font:14px system-ui}
      h2{font-size:18px;margin:0 0 8px}p{line-height:1.6;color:#b9c8dc}textarea{width:100%;height:165px;resize:vertical;background:#0d1420;color:white;border:1px solid #46536a;border-radius:10px;padding:12px;font:14px system-ui}
      button{padding:10px 14px;border:0;border-radius:9px;background:#9de8d0;color:#10261f;cursor:pointer;font-weight:700}button:disabled{opacity:.5;cursor:wait}.row{display:flex;gap:8px;margin-top:12px}.secondary{background:#354256;color:white}output{display:block;margin-top:14px;line-height:1.6;white-space:pre-wrap}small{color:#b9c8dc}
    </style>
    <section><h2>AIR 나레이션 <small>실험 버전</small></h2>
    <p>Gemini 읽어주기를 음성 파일로 저장합니다.<br>현재 대화에 시험 문장이 추가됩니다.</p>
    <textarea aria-label="나레이션 대본" placeholder="나레이션 문장을 입력하세요 (최대 2,000자)" maxlength="2000"></textarea>
    <div class="row"><button id="run">음성 생성·저장</button><button id="hide" class="secondary">접기</button></div>
    <output role="status">대기 중 · API 키 없이 Gemini 웹 사용</output></section>`;
  document.documentElement.append(host);
  const status = text => { root.querySelector('output').textContent = text; };
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const normalize = s => s.replace(/\s+/g, ' ').trim();
  const visible = e => e && e.getClientRects().length > 0;
  const button = (scope, names) => [...scope.querySelectorAll('button,[role="menuitem"]')].find(e => visible(e) && names.includes((e.getAttribute('aria-label') || e.textContent).trim()));
  const waitFor = async (fn, timeout = 90000) => {
    const until = Date.now() + timeout;
    while (Date.now() < until) { const value = fn(); if (value) return value; await delay(300); }
    throw new Error('대기 시간이 초과됐습니다. 로그인·생성 제한·화면 변경을 확인하세요.');
  };
  root.querySelector('#hide').onclick = () => { host.hidden = true; };
  chrome.runtime.onMessage.addListener(message => { if (message.type === 'air-show') host.hidden = false; });
  let busy = false;
  async function run(text) {
    if (busy) throw new Error('진행 중인 작업이 있습니다.');
    if (!text.trim() || text.length > 2000) throw new Error('1~2,000자의 나레이션을 입력하세요.');
    busy = true;
    const id = crypto.randomUUID();
    root.querySelector('#run').disabled = true;
    let listener;
    try {
      const input = document.querySelector('[contenteditable="true"][aria-label="Gemini 프롬프트 입력"], [contenteditable="true"][aria-label="Enter a prompt for Gemini"]');
      if (!visible(input)) throw new Error('Gemini 입력창이 보이지 않습니다. 다른 오버레이를 닫아 주세요.');
      if (input.textContent.trim()) throw new Error('작성 중인 Gemini 입력이 있습니다. 전송하거나 비운 뒤 실행하세요.');
      const existing = new Set(document.querySelectorAll('message-content'));
      status('1/4 · Gemini에 나레이션 전달 중');
      input.focus();
      document.execCommand('insertText', false, `다음 원문을 수정하거나 설명하지 말고 그대로 한 번만 출력하세요. 제목, 따옴표, 마크다운을 추가하지 마세요.\n\n${text}`);
      const submit = await waitFor(() => button(document, ['메시지 보내기', '전송', 'Send message', 'Submit']), 5000);
      submit.click();
      let stableText = '', stableAt = 0;
      const response = await waitFor(() => {
        const nodes = [...document.querySelectorAll('message-content')].filter(e => !existing.has(e));
        const node = nodes.at(-1);
        if (!node) return null;
        const value = normalize(node.innerText);
        if (value !== stableText) { stableText = value; stableAt = Date.now(); }
        const generating = button(document, ['대답 생성 중지', 'Stop response']);
        return value && !generating && Date.now() - stableAt > 1500 ? node : null;
      });
      if (normalize(response.innerText) !== normalize(text)) throw new Error('Gemini 응답이 원문과 달라 저장을 중단했습니다.');
      status('2/4 · 원문 확인 완료, 음성 재생 준비');
      // Restrict the action search to the newly generated response turn.
      let turn = response;
      while (turn && !button(turn, ['옵션 더보기', 'More'])) turn = turn.parentElement;
      const more = turn && button(turn, ['옵션 더보기', 'More']);
      if (!more) throw new Error('새 응답의 읽어주기 메뉴를 찾지 못했습니다.');
      more.click();
      const listen = await waitFor(() => button(document, ['듣기', 'Listen']), 5000);
      const audioPromise = new Promise((resolve, reject) => {
        listener = event => {
          if (event.source !== window || event.origin !== location.origin || event.data?.channel !== 'air-narrator-audio' || event.data.id !== id) return;
          if (event.data.type === 'audio') resolve(event.data.dataUrl);
          if (event.data.type === 'error') reject(new Error(event.data.message));
        };
        window.addEventListener('message', listener);
      });
      window.postMessage({channel: 'air-narrator-control', type: 'arm', id}, location.origin);
      await delay(50);
      listen.click();
      status('3/4 · 음성 재생·파일 확보 중');
      let timer;
      const dataUrl = await Promise.race([audioPromise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('오디오 확보 시간 초과. 현재 재생 방식은 추가 지원이 필요합니다.')), 240000); })]).finally(() => clearTimeout(timer));
      const result = await chrome.runtime.sendMessage({type: 'air-save', id, dataUrl});
      if (!result?.ok) throw new Error(result?.error || '파일 저장 실패');
      status('4/4 · 다운로드 완료 확인 중');
      const key = `download-${result.downloadId}`;
      let complete = false;
      for (let i = 0; i < 120; i++) {
        const entry = (await chrome.storage.local.get(key))[key];
        if (entry?.state === 'interrupted') throw new Error('다운로드가 중단됐습니다.');
        if (entry?.state === 'complete') { complete = true; break; }
        await delay(500);
      }
      if (!complete) throw new Error('다운로드 완료를 확인하지 못했습니다. Chrome 다운로드를 확인하세요.');
      status('저장 완료 · 다운로드/AIR-Narration\n워커 자동 연결은 다음 검증 단계입니다.');
    } finally {
      window.postMessage({channel: 'air-narrator-control', type: 'disarm', id}, location.origin);
      if (listener) window.removeEventListener('message', listener);
      busy = false;
      root.querySelector('#run').disabled = false;
    }
  }
  root.querySelector('#run').onclick = () => run(root.querySelector('textarea').value).catch(error => status(`중단 · ${error.message}`));
})();
