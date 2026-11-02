"""Translate the existing 3386 narration using only the local Codex worker."""
import hashlib, json, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore
from worker.codex_subtitle_translation import translate_blocks
from codex_content_runner import CodexStagedContentRunner
from worker.script_topic_delivery import write

OUT=ROOT/'output/codex-local-console/d57947df4af3479b85185c7ca0610a60/actual-production'
OUT.mkdir(parents=True,exist_ok=True)
store=ScriptStore();runner=CodexStagedContentRunner()
def status(stage,state='running',**extra):
    write(OUT/'translation-status.json',{'stage':stage,'status':state,'updated_at':time.time(),**extra})
def get_topic():
    rows,_=store.request('GET','topics_queue',params={'select':'*','id':'eq.3386'})
    if len(rows)!=1:raise ValueError('토픽을 찾지 못했습니다.')
    row=rows[0]
    if row.get('status')!='pending' or row.get('assigned_at') or row.get('assigned_employee_email'):
        raise ValueError('토픽 배정·취소 상태가 변경됐습니다.')
    if (row.get('progress_payload') or {}).get('source_script_job_id')!='d57947df4af3479b85185c7ca0610a60':
        raise ValueError('토픽 출처가 변경됐습니다.')
    return row
try:
    topic=get_topic();scenes=topic['pregenerated_structure']['scenes'];script=topic['pregenerated_script']
    sha=hashlib.sha256(script.encode()).hexdigest()
    blocks=[{'index':i,'source_text':str(s.get('scene_text') or s.get('narration') or '').strip()}
            for i,s in enumerate(scenes)]
    if len(blocks)!=104 or any(not b['source_text'] for b in blocks):raise ValueError('원본 씬 대본 누락')
    if '\n\n'.join(b['source_text'] for b in blocks)!=script:raise ValueError('원본 씬과 대본 불일치')
    translations={}
    for lang in ('ko','th'):
        status('한국어 대본 번역' if lang=='ko' else '태국어 대본 번역')
        target=OUT/('script-translation-'+lang+'.json')
        if target.exists():
            result=json.loads(target.read_text(encoding='utf-8'))
            if result.get('source_script_sha256')!=sha:raise ValueError('저장된 번역의 원본이 바뀌었습니다.')
        else:
            rows=translate_blocks(runner,'topic-3386-script-'+lang,blocks,lang)
            result={'version':1,'source_script_sha256':sha,'source_language':'ja','target_language':lang,
                    'scope':'scene_narration','blocks':rows,'updated_at':time.time()}
            write(target,result)
        translations[lang]=result
    status('번역 저장 및 재조회')
    now=get_topic()
    if hashlib.sha256(now['pregenerated_script'].encode()).hexdigest()!=sha:raise ValueError('원본 대본이 변경됐습니다.')
    progress=now.get('progress_payload') or {};progress['script_translations']=translations
    rows,_=store.request('PATCH','topics_queue',params={'id':'eq.3386','status':'eq.pending',
        'assigned_at':'is.null','assigned_employee_email':'eq.',
        'progress_payload->>source_script_job_id':'eq.d57947df4af3479b85185c7ca0610a60'},
        body={'progress_payload':progress},prefer='return=representation')
    if len(rows)!=1:raise ValueError('조건부 번역 저장 실패')
    saved=get_topic(); actual=(saved.get('progress_payload') or {}).get('script_translations') or {}
    if any(actual.get(lang)!=translations[lang] for lang in ('ko','th')):raise ValueError('번역 재조회 불일치')
    status('한국어·태국어 대본 번역 저장 완료','completed',scene_count=len(blocks),source_sha256=sha)
except Exception as exc:
    write(OUT/'translation-error.json',{'message':str(exc),'traceback':traceback.format_exc(),'updated_at':time.time()})
    status('대본 번역 중단','failed',error=str(exc))
