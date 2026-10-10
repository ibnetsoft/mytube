"""Voice Studio view, embedded into the worker dashboard at render time."""
PANEL = r'''
<style>#tab-voice-studio [hidden] {display:none!important} #tab-voice-studio input, #tab-voice-studio select {background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:8px}</style>
<div class="tab-content" id="tab-voice-studio">
 <h2>대본에 어울리는 목소리 찾기</h2>
 <p class="info">Gemini 목소리 30개 · 남성 16개 / 여성 14개 · 한국어 샘플</p>
 <div class="status-card" style="margin:16px 0;display:grid;gap:12px">
  <label>저장된 대본 <select id="vs-script-list" onchange="vsLoadScript()"><option value="">대본을 선택하세요</option></select></label>
  <textarea id="vs-script" rows="6" placeholder="목록에서 선택한 대본이 자동으로 표시됩니다. 여기서 고친 내용은 이번 음성 생성에만 사용됩니다." style="width:100%;background:#0d1117;color:#e6edf3;padding:12px;border:1px solid #30363d;border-radius:8px"></textarea>
  <div style="display:flex;gap:16px;flex-wrap:wrap">
   <label>목소리 <strong id="vs-selected">Charon</strong></label>
   <label>속도 <input id="vs-speed" type="number" min="0.7" max="1.3" step="0.05" value="1" style="width:75px"></label>
   <label>대사 처리 <select id="vs-dialogue"><option value="elevenlabs">ElevenLabs로 대사 생성</option><option value="narrator">선택한 Gemini 목소리로 전체 낭독</option></select></label>
  </div>
  <label>말투·감정 <input id="vs-direction" maxlength="1500" value="따뜻하고 차분한 한국어 이야기 낭독." style="width:100%" placeholder="예: 담담한 중년 화자처럼, 긴장감을 서서히 높이며"></label>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
   <button class="btn" onclick="vsSave()">이 대본에 목소리 저장</button>
   <button class="btn btn-primary" id="vs-generate" onclick="vsGenerate()">선택한 설정으로 음성 생성</button>
  </div>
  <div class="info">대본별 저장은 다음 음성 생성에 적용됩니다. 기존 음성을 바꾸려면 음성 생성을 누르세요. 큰따옴표 안을 대사로 구분하며, ElevenLabs 사용분은 별도 과금됩니다.</div>
 </div>
 <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0">
  <input id="vs-search" placeholder="목소리 이름 검색" oninput="vsDraw()">
  <select id="vs-gender" onchange="vsDraw()"><option value="">남성·여성 모두</option><option>남성</option><option>여성</option></select>
  <span class="info" id="vs-count"></span>
 </div>
 <p class="info">샘플은 동일한 문장을 차분하게 읽습니다. 처음 생성할 때 Cloud 사용료가 발생하며, 다시 들으면 저장된 음성을 재사용합니다.</p>
 <div id="vs-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px"></div>
 <div class="status-card" style="margin-top:16px;position:sticky;bottom:12px;background:#161b22;z-index:2">
  <div id="vs-status" role="status" aria-live="polite">듣고 싶은 목소리의 샘플 듣기를 누르세요.</div>
  <audio id="vs-player" controls style="width:100%;margin-top:12px" hidden></audio>
  <a id="vs-download" class="btn" hidden download="narration.wav">음성 다운로드</a>
 </div>
</div>
'''

JS = r'''
let vsVoices = [], vsVoice = 'Charon', vsKey = '', vsBusy = false, vsLoaded = false;
async function vsRequest(path, method='GET', body) {
 const response = await fetch('/api/voice-studio' + path, {method, headers:{'Content-Type':'application/json','X-Voice-Studio':'1'}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
 const data = await response.json();
 if (!response.ok) throw new Error(data.detail || '요청에 실패했습니다.');
 return data;
}
function vsStatus(message) { document.getElementById('vs-status').textContent=message; }
async function loadVoiceStudio() {
 try {
  if (!vsLoaded) { vsVoices=(await vsRequest('/voices')).voices; vsLoaded=true; vsDraw(); }
  const response=await fetch('/api/generated-results?limit=500');
  if (!response.ok) throw new Error('대본 목록을 불러오지 못했습니다.');
  const rows=(await response.json()).results || [];
  const select=document.getElementById('vs-script-list'), previous=select.value;
  select.innerHTML='<option value="">대본을 선택하세요</option>';
  rows.filter(r=>r.has_script).forEach(r=>{ const option=document.createElement('option'); option.value=r.id; option.textContent=r.title || r.topic || r.id; select.append(option); });
  select.value=previous;
 } catch(e) { vsStatus(e.message); }
}
function vsDraw() {
 const filter=document.getElementById('vs-search').value.toLowerCase(), gender=document.getElementById('vs-gender').value;
 const rows=vsVoices.filter(v=>v.name.toLowerCase().includes(filter)&&(!gender||v.gender===gender));
 document.getElementById('vs-count').textContent=rows.length+'개';
 const grid=document.getElementById('vs-grid'); grid.replaceChildren();
 rows.forEach(v=>{
  const card=document.createElement('div'); card.className='status-card'; card.style.borderColor=v.name===vsVoice?'#58a6ff':'#30363d';
  const title=document.createElement('strong'); title.textContent=v.name+' · '+v.gender; card.append(title);
  const actions=document.createElement('div'); actions.style='display:flex;gap:8px;margin-top:12px';
  const listen=document.createElement('button'); listen.className='btn btn-sm'; listen.textContent='샘플 듣기'; listen.disabled=vsBusy; listen.onclick=()=>vsSample(v.name);
  const choose=document.createElement('button'); choose.className='btn btn-sm'; choose.textContent=v.name===vsVoice?'선택됨':'선택'; choose.setAttribute('aria-pressed',String(v.name===vsVoice)); choose.onclick=()=>{vsVoice=v.name;document.getElementById('vs-selected').textContent=v.name;vsDraw();};
  actions.append(listen,choose);card.append(actions);grid.append(card);
 });
}
async function vsLoadScript() {
 const id=document.getElementById('vs-script-list').value; vsKey='';
 document.getElementById('vs-script').value='';
 if (!id) return;
 try {
  const response=await fetch('/api/generated-results/'+encodeURIComponent(id));
  if (!response.ok) throw new Error('대본을 불러오지 못했습니다.');
  const data=await response.json();
  if (document.getElementById('vs-script-list').value!==id) return;
  const key=data.topic_queue_id != null && String(data.topic_queue_id) ? 'topic_'+data.topic_queue_id : id;
  const {choice}=await vsRequest('/choice/'+encodeURIComponent(key));
  if (document.getElementById('vs-script-list').value!==id) return;
  vsKey=key; document.getElementById('vs-script').value=data.script||'';
  const value=choice||{voice:'Charon',speed:1,direction:'따뜻하고 차분한 한국어 이야기 낭독.',dialogue_mode:'elevenlabs'};
  vsVoice=value.voice; document.getElementById('vs-selected').textContent=vsVoice;
  document.getElementById('vs-speed').value=value.speed;document.getElementById('vs-direction').value=value.direction;
  document.getElementById('vs-dialogue').value=value.dialogue_mode;vsDraw();
  vsStatus(choice?'이 대본에 저장한 목소리를 불러왔습니다.':'대본을 불러왔습니다. 목소리를 선택해 주세요.');
 } catch(e) {vsStatus(e.message);}
}
function vsChoice() {return {voice:vsVoice,speed:Number(document.getElementById('vs-speed').value),direction:document.getElementById('vs-direction').value,dialogue_mode:document.getElementById('vs-dialogue').value};}
async function vsSave() {
 if (!vsKey) {vsStatus('먼저 저장할 대본을 목록에서 선택해 주세요.');return;}
 try {await vsRequest('/choice/'+encodeURIComponent(vsKey),'PUT',vsChoice());vsStatus('이 대본의 목소리 설정을 저장했습니다.');}catch(e){vsStatus(e.message);}
}
async function vsRun(path,body,label) {
 if(vsBusy)return;vsBusy=true;vsDraw();document.getElementById('vs-generate').disabled=true;
 const player=document.getElementById('vs-player'); player.pause();player.hidden=true;document.getElementById('vs-download').hidden=true;
 try {
  vsStatus(label+' 준비 중…');let job=await vsRequest(path,'POST',body);
  while(['queued','generating'].includes(job.status)){await new Promise(r=>setTimeout(r,1500));job=await vsRequest('/jobs/'+job.id);vsStatus(label+' 생성 중…');}
  if(job.status!=='complete')throw new Error(job.error||'음성 생성 실패');
  player.src=job.audio_url;player.hidden=false;
  const link=document.getElementById('vs-download');link.href=job.audio_url;link.hidden=false;
  vsStatus(label+' · '+job.duration_seconds.toFixed(1)+'초 · 준비 완료');
  player.play().catch(()=>vsStatus(label+' 준비 완료. 재생 버튼을 눌러 주세요.'));
 }catch(e){vsStatus(e.message);}finally{vsBusy=false;vsDraw();document.getElementById('vs-generate').disabled=false;}
}
function vsSample(name){return vsRun('/sample/'+encodeURIComponent(name),undefined,name+' 샘플');}
function vsGenerate(){const script=document.getElementById('vs-script').value;if(!script.trim()){vsStatus('대본을 선택해 주세요.');return;}return vsRun('/generate',{script,choice:vsChoice()},vsVoice+' 대본 음성');}
'''


def inject(html):
    nav = '<div class="nav-item" data-tab="voice-studio" data-worker-scope="script" onclick="switchTab(\'voice-studio\')"><span class="icon">♫</span> Voice Studio</div>'
    html = html.replace('<div class="nav-item" data-tab="voicebox-tts"', nav + '\n<div class="nav-item" data-tab="voicebox-tts"', 1)
    html = html.replace('<div class="tab-content" id="tab-voicebox-tts">', PANEL + '\n<div class="tab-content" id="tab-voicebox-tts">', 1)
    html = html.replace("'voicebox-tts': 'Voicebox TTS 음성 생성',", "'voice-studio': 'Voice Studio · 목소리 선택',\n  'voicebox-tts': 'Voicebox TTS 음성 생성',", 1)
    html = html.replace("  'voicebox-tts',", "  'voice-studio',\n  'voicebox-tts',", 1)
    html = html.replace("if (tabId === 'voicebox-tts')", "if (tabId === 'voice-studio') loadVoiceStudio();\n  if (tabId === 'voicebox-tts')", 1)
    before, after = html.rsplit('</script>', 1)
    return before + JS + "\nif(location.hash === '#voice-studio') switchTab('voice-studio');\n</script>" + after
