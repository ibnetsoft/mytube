"""Prompt-only fifth manual stage; no paid generation on the script worker."""
import json,math,re
TASK='''Prepare ONLY English ElevenLabs sound-effect prompts for the approved cut plan. Return {cues:[{id,cut_id,prompt,duration_seconds,offset_seconds,volume_db,reason}],quality_notes:[]}. Sparse selection; zero cues is valid. id must be unique ASCII, cut_id must exactly match an approved image cut. Prompt describes isolated non-speech Foley or designed sound, actual materials/contact, no music or human speech. Never read lettering aloud. duration_seconds is 0.5..30, offset_seconds is a nonnegative cut-relative event offset, volume_db is -60..0. Do not claim actual contact timing from unreviewed images/video; choose cut start only when the depicted event starts there and flag uncertain anchors for user review. Preserve existing user audio cues. Do not generate sounds, call ElevenLabs, render, or publish. Final placement uses the submitted recorded scene clock and trims sound at its cut boundary without extending scenes.'''
def validate_output(value,workflow):
 rows=value.get('cues');known={r['cut_id'] for r in workflow['stages'][1]['output']['cuts']}
 if not isinstance(rows,list) or len(rows)>120 or len(json.dumps(value))>600000:raise ValueError('효과음 프롬프트 수·크기를 확인하세요.')
 seen=set()
 for row in rows:
  ident=row.get('id');text=row.get('prompt')
  if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',ident) or ident in seen or row.get('cut_id') not in known:raise ValueError('효과음 ID와 확정 컷 연결을 확인하세요.')
  seen.add(ident)
  if not isinstance(text,str) or not 1<=len(text.strip())<=2000 or not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('효과음 프롬프트와 선택 근거가 필요합니다.')
  for key,low,high in [('duration_seconds',.5,30),('offset_seconds',0,3600),('volume_db',-60,0)]:
   n=row.get(key)
   if type(n) not in (int,float) or not math.isfinite(n) or not low<=n<=high:raise ValueError('효과음 길이·위치·음량을 확인하세요.')
