"""Read-only narration diagnostics; never rewrite speech by suffix matching."""
import re

def diagnose(sections):
 narration=[];dialogue=[];longest=run=0;reporting=[]
 for i,s in enumerate(sections,1):
  for b in s.get('spoken_blocks',s.get('blocks',[])):
   text=str(b.get('text') or '').strip()
   if b.get('kind')=='dialogue':dialogue.append(text);continue
   if b.get('kind')!='narration':continue
   for part in re.split(r'(?<=[.!?。！？])\s*',text):
    if not part.strip():continue
    quote=part.strip();formal=bool(re.search(r'습니다[.!?]?[”’\"]?$',quote))
    row={'scene_order':s.get('scene_order',i),'scene_id':s.get('id'),'block_id':b.get('id'),'quote':quote,'formal_korean_ending':formal}
    narration.append(row);run=run+1 if formal else 0;longest=max(longest,run)
    if formal:reporting.append(row)
 nc=sum(len(str(b.get('text') or '')) for s in sections for b in s.get('spoken_blocks',s.get('blocks',[])) if b.get('kind')=='narration')
 dc=sum(map(len,dialogue));total=nc+dc
 return {'scope':'text diagnostics, not semantic deletion or audio audition','narration_sentences':len(narration),'formal_korean_ending_sentences':len(reporting),'formal_korean_ending_ratio':len(reporting)/len(narration) if narration else 0,'longest_formal_narration_run':longest,'narration_characters':nc,'dialogue_characters':dc,'narration_character_share':nc/total if total else 0,'dialogue_blocks':len(dialogue),'formal_examples':reporting[:12],'automatic_rewrite':False}
