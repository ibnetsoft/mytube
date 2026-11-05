# -*- coding: utf-8 -*-
import re,json
from pathlib import Path
P=Path(__file__).parent
roles={'내레이션':None,'수색 무사':'guard','보초 무사':'lookout_guard','서진':'seojin','도겸':'dogyeom','서리':'clerk','철산문 무사':'checkpoint_guard','수레꾼':'carter','길목 무사':'checkpoint_guard'}
s=(P/'approved-draft.md').read_text();body=s[s.index('### 01.'):s.index('**— 3화 끝 —**')];scenes=[]
for segment in re.split(r'^### ',body,flags=re.M)[1:]:
 lines=segment.splitlines();n=int(lines[0].split('.')[0]);blocks=[];who=None;buffer=[]
 def flush():
  if buffer:
   text=' '.join(x.strip()for x in buffer).strip();kind='narration' if who is None else 'dialogue';b={'kind':kind,'text':text}
   if who:b['speaker']=who
   if who and re.search(r'“[^”]*”',text):
    cursor=0
    for match in re.finditer(r'“[^”]*”',text):
     if text[cursor:match.start()].strip():blocks.append({'kind':'narration','text':text[cursor:match.start()].strip()})
     blocks.append({'kind':'dialogue','speaker':who,'text':match.group()});cursor=match.end()
    if text[cursor:].strip():blocks.append({'kind':'narration','text':text[cursor:].strip()})
   else:blocks.append(b)
   buffer.clear()
 for line in lines[1:]:
  if line.startswith('>'):continue
  if line.startswith('**'):
   flush();label=line.strip('*').split(' — ')[0];assert label in roles,label;who=roles[label]
  elif line.strip():buffer.append(line)
 flush();scenes.append({'id':f'E03_S{n:02d}','blocks':blocks})
assert len(scenes)==20
(P/'approved-blocks.json').write_text(json.dumps(scenes,ensure_ascii=False,indent=2));print('Approved spoken blocks',sum(len(s['blocks'])for s in scenes))

# Quoted dialogue on a labeled line may be followed by narrative. Never assign the trailing narration to the speaker.
# Final boundary repair and registration purity gate are mandatory: repair_dialogue_boundary.py.
