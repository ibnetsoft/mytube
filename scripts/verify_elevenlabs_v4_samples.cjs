const fs = require('node:fs'), path = require('node:path'), cp = require('node:child_process');
const assert = require('node:assert/strict');
const runtime = require('./std_web_runtime.cjs');
const out = path.join(runtime.root, '_dev/artifacts/elevenlabs-v4-comparison');
const report = JSON.parse(fs.readFileSync(path.join(out, 'report.json'), 'utf8'));
const timestamp = n => new Date(Math.round(n * 1000)).toISOString().slice(11, 23);
async function main() {
  const key = (await runtime.load('elevenLabsKeys').getConfiguredElevenLabsKeys())[0];
  const results = [];
  for (const entry of report.results) {
    const stem = `${entry.language}-${entry.model}`;
    const file = path.join(out, `${stem}.mp3`);
    const transcriptFile = path.join(out, `${stem}-transcript.json`);
    let transcript;
    if (fs.existsSync(transcriptFile)) transcript = JSON.parse(fs.readFileSync(transcriptFile, 'utf8'));
    else {
      const form = new FormData();
      form.set('file', new Blob([fs.readFileSync(file)], { type: 'audio/mpeg' }), `${stem}.mp3`);
      form.set('model_id', 'scribe_v2'); form.set('language_code', entry.language);
      form.set('tag_audio_events', 'false');
      const res = await fetch('https://api.elevenlabs.io/v1/speech-to-text', { method: 'POST', headers: { 'xi-api-key': key }, body: form });
      if (!res.ok) {
        transcript = { text: null, unavailable: `HTTP ${res.status}: ${(await res.text()).slice(0, 350)}` };
      } else transcript = await res.json();
      fs.writeFileSync(transcriptFile, JSON.stringify(transcript, null, 2));
    }
    const pcm = cp.execFileSync(process.env.FFMPEG_PATH, ['-v','error','-i',file,'-f','s16le','-ar','44100','-ac','1','pipe:1'], {maxBuffer:10*1024*1024});
    const decodedDuration = pcm.length / 2 / 44100;
    const end = entry.timeline.at(-1).end;
    const driftMs = Math.abs(decodedDuration - end) * 1000;
    assert(driftMs < 40, `${stem}: decoded audio drifts ${driftMs}ms from subtitle timeline`);
    const windows = entry.timeline.map((row, i) => {
      assert.equal(row.start, i ? entry.timeline[i-1].end : 0);
      const alignment = entry.alignment[i];
      const spokenEnd = Math.max(...alignment.character_end_times_seconds);
      const lastSpeechEnd = Math.max(...alignment.characters.flatMap((char, j) => /[\p{L}\p{N}]/u.test(char) ? [alignment.character_end_times_seconds[j]] : []));
      assert(lastSpeechEnd <= row.end-row.start, `${stem}: spoken characters extend past subtitle boundary`);
      // Provider character timestamps include a small codec/rounding tail.
      // The application uses actual MP3 frame lengths, never these timestamps.
      assert(spokenEnd <= row.end-row.start+0.08, `${stem}: provider alignment exceeds subtitle window by over 80ms`);
      assert.equal(entry.synced[i].start_num, row.start);
      assert.equal(entry.synced[i].end_num, row.end);
      return { start: row.start, end: row.end, alignmentStart: row.start+alignment.character_start_times_seconds[0], alignmentEnd: row.start+spokenEnd,
        alignmentTailMs: (spokenEnd-(row.end-row.start))*1000 };
    });
    fs.writeFileSync(path.join(out, `${stem}.vtt`), 'WEBVTT\n\n'+entry.timeline.map((row,i)=>`${i+1}\n${timestamp(row.start)} --> ${timestamp(row.end)}\n${row.text}\n`).join('\n'));
    const result = {language:entry.language,model:entry.model,decodedDuration,timelineDuration:end,driftMs,windows,transcript:transcript.text,transcriptionUnavailable:transcript.unavailable};
    results.push(result); console.log(JSON.stringify(result));
  }
  fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify(results,null,2));
  const escape = s => s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
  const cards = report.results.map((entry,i)=>`<article><h2>${entry.language==='ko'?'한국어':'日本語'} · ${entry.model==='eleven_v4'?'Eleven v4':'Multilingual v2'}</h2><p>${entry.timeline.at(-1).end.toFixed(3)}초 · 길이/자막 오차 ${results[i].driftMs.toFixed(1)}ms</p><audio controls preload="metadata" src="${entry.language}-${entry.model}.mp3"></audio><div class="subtitle" aria-live="polite">재생하면 현재 자막이 표시됩니다.</div><ol>${entry.timeline.map(r=>`<li>${escape(r.text)}</li>`).join('')}</ol><a href="${entry.language}-${entry.model}.vtt">자막 VTT</a></article>`).join('');
  fs.writeFileSync(path.join(out,'comparison.html'), `<!doctype html><html lang="ko"><meta charset="utf-8"><title>ElevenLabs v2 / v4 비교</title><style>body{background:#10151f;color:#eef2fa;font:16px system-ui;margin:40px auto;max-width:1100px;padding:20px}h1{font-size:28px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{padding:22px;background:#1c2636;border-radius:16px}h2{font-size:20px}audio{width:100%}.subtitle{min-height:90px;padding:18px;background:#10151f;border-radius:8px;margin:18px 0;line-height:1.7}li{line-height:1.6;margin-bottom:8px;color:#aebbd0}li.active{color:#6ee7d0}a{color:#7dd3fc}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style><h1>ElevenLabs v2 / v4 — 같은 성우 비교</h1><p>Laura · 같은 언어 안에서 대본 동일 · speed 1 / stability 0.7 / style 0.45 / similarity 0.75</p><p>실제 앱의 MP3 합치기·녹음 길이 기반 자막 계산 함수를 사용했습니다. 자막은 구간 단위이며 단어별 강제 정렬 결과가 아닙니다. 자연스러움은 아래 음성으로 직접 비교해 주세요.</p><div class="grid">${cards}</div><script>const entries=${JSON.stringify(report.results.map(e=>e.timeline))};document.querySelectorAll('article').forEach((card,i)=>{const audio=card.querySelector('audio');audio.addEventListener('play',()=>document.querySelectorAll('audio').forEach(a=>{if(a!==audio)a.pause()}));audio.addEventListener('timeupdate',()=>{const at=entries[i].findIndex(r=>audio.currentTime>=r.start&&audio.currentTime<r.end);card.querySelector('.subtitle').textContent=at<0?'':entries[i][at].text;card.querySelectorAll('li').forEach((li,j)=>li.classList.toggle('active',j===at))})})</script></html>`);
}
main().catch(e=>{console.error(e);process.exitCode=1});
