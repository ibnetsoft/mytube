"""Strict per-block translation via existing local Codex stage; no external AI API."""
import json
from draft_3292_scoped import OUT,save
from codex_content_runner import CodexStagedContentRunner,CodexContentConfig
rows=json.loads((OUT/'subtitles.json').read_text(encoding='utf-8'))
r=CodexStagedContentRunner(CodexContentConfig.from_environment());translated=[]
for start in range(0,len(rows),55):
    batch=[{'index':i,'source_text':rows[i]['text'],'scene_number':rows[i]['scene_number']} for i in range(start,min(start+55,len(rows)))]
    print('Thai translation batch '+str(start),flush=True)
    v=r._stage('3292_final_thai',f'02_thai_{start}',{'blocks':batch,'names':{'연이':'ยอนอี','순덕':'ซุนด็อก','금례':'กึมรเย','최 서방':'นายชเว','최 부자':'เศรษฐีชเว','훈장':'ครูประจำหมู่บ้าน'}},
        'Translate Korean subtitle blocks into natural Thai. Preserve exactly ONE translated block per source block; no merge/split/omission/summary, no added facts. Adjacent fragments form connected sentences, maintain names and relations. Return {blocks:[{index:0,translated_text:"..."}]}. Include every index exactly once in original order. Translate actual text only; do not add speaker labels.')
    assert [x['index'] for x in v['blocks']]==[x['index'] for x in batch]
    for src,t in zip(batch,v['blocks']):
        assert str(t['translated_text']).strip()
        translated.append({**src,'translated_text':t['translated_text'].strip()})
save('thai-translations.json',{'language':'th','blocks':translated,'source':'codex-final-repair','block_count':len(translated)})
print('Thai complete '+str(len(translated)),flush=True)
