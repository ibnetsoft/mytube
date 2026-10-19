const fs = require('node:fs');
const path = require('node:path');
const runtime = require('./std_web_runtime.cjs');
const out = path.join(runtime.root, '_dev/artifacts/elevenlabs-v4-comparison');
const voiceId = 'FGY2WhTYpPnrIDTdsKH5';
const scripts = {
  ko: ['비가 그친 골목에 작은 불빛이 켜졌습니다. 지수는 걸음을 멈추고 조용히 문을 바라보았습니다.', '정말 여기 있는 거야? 잠시 망설이던 그녀는 숨을 고르고, 천천히 문을 두드렸습니다.'],
  ja: ['雨がやんだ路地に、小さな明かりがともりました。美咲は足を止め、静かに扉を見つめました。', '本当に、ここにいるの？ 少しためらった彼女は、ひと息ついて、ゆっくりと扉をたたきました。'],
};
async function main() {
  fs.mkdirSync(out, { recursive: true });
  const keys = await runtime.load('elevenLabsKeys').getConfiguredElevenLabsKeys();
  if (!keys.length) throw new Error('No configured ElevenLabs key');
  const report = { voiceId, settings: { stability: 0.7, similarity_boost: 0.75, style: 0.45, speed: 1 }, results: [] };
  for (const [language, rows] of Object.entries(scripts)) {
    for (const model of ['eleven_multilingual_v2', 'eleven_v4']) {
      const segments = [];
      for (let i = 0; i < rows.length; i++) {
        const stem = `${language}-${model}-${i + 1}`;
        const jsonPath = path.join(out, `${stem}.json`);
        let data;
        if (fs.existsSync(jsonPath)) data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
        else {
          const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voiceId}/with-timestamps?output_format=mp3_44100_128`, {
            method: 'POST', headers: { 'xi-api-key': keys[0], 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: rows[i], model_id: model, voice_settings: report.settings }),
          });
          if (!res.ok) throw new Error(`${stem}: ${res.status} ${(await res.text()).slice(0, 500)}`);
          data = await res.json();
          fs.writeFileSync(path.join(out, `${stem}.mp3`), Buffer.from(data.audio_base64, 'base64'));
          delete data.audio_base64;
          fs.writeFileSync(jsonPath, JSON.stringify(data, null, 2));
        }
        segments.push({ text: rows[i], voiceId, file: path.join(out, `${stem}.mp3`), alignment: data.alignment || data.normalized_alignment });
        console.log(`ready ${stem}`);
      }
      const assembled = await runtime.load('stdStoredNarration').assembleStoredNarration(segments, {
        resolve: async (_, i) => ({ asset: segments[i], cached: true }),
        read: async asset => fs.readFileSync(asset.file),
      }, { allowGenerate: false });
      const synced = runtime.load('stdRecordedSubtitleTiming').applyRecordedSubtitleTiming(rows.map(text => ({text, voice_id: voiceId})), assembled.timeline);
      fs.writeFileSync(path.join(out, `${language}-${model}.mp3`), assembled.audioBuffer);
      const entry = { language, model, timeline: assembled.timeline, synced, alignment: segments.map(s => s.alignment) };
      report.results.push(entry);
      fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
      console.log(`assembled ${language} ${model}: ${assembled.timeline.at(-1).end.toFixed(3)}s`);
    }
  }
}
main().catch(e => { console.error(e.message); process.exitCode = 1; });
