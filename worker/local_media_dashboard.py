"""Read-only, bounded queue summary for the loopback worker dashboard."""
import os
import threading
import time
from datetime import datetime, timezone

_connections = threading.local()

# Reviewed Korean titles, keyed by the exact source so edited titles never reuse a stale translation.
_PREPARED_KO = {
    '【江戸人情噺】夜ごと隠居所を訪ねる十七歳の娘――大黒屋三千両の秘密': '【에도 인정 이야기】밤마다 은거처를 찾는 열일곱 살 소녀 ― 다이코쿠야 삼천 냥의 비밀',
    '追い出した友が、向かいの宿にいた｜信州宿場の人情噺': '쫓아낸 친구가 맞은편 여관에 있었다｜신슈 역참마을의 인정 이야기',
    '[E2E TEST] 日本歴史・ナレーションのみ・駿府': '[E2E TEST] 일본 역사 · 내레이션만 · 슨푸',
}

def korean_title(project, topic=None):
    title = project.get('title') or ''
    for payload in (topic or {}, project.get('source_titles') or {}, project.get('project_titles') or {}):
        for translations in (payload.get('title_translations'), payload.get('progress_titles'), payload.get('structure_titles'), payload.get('metadata_titles')):
            value = (translations or {}).get('ko')
            if isinstance(value, str) and value.strip() and value.strip() != title:
                return value.strip()
    return _PREPARED_KO.get(title, '')


def query_session():
    # Reuse TLS connections and retry only read requests after transient failures.
    if not hasattr(_connections, 'session'):
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        session = requests.Session()
        session.mount('https://', HTTPAdapter(max_retries=Retry(
            total=2, backoff_factor=.4, status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset(('GET',)), respect_retry_after_header=False,
        )))
        _connections.session = session
    return _connections.session

def group(state):
    if state in ('ready', 'reviewed', 'completed', 'complete'): return 'completed'
    if state in ('failed', 'obsolete', 'cancelled', 'canceled'): return 'failed'
    if state in ('draft', 'prepared', 'approved', 'needs_review', 'direction_pending', 'review_pending'): return 'review'
    if state in ('processing', 'rendering'): return 'working'
    return 'waiting'

def summarize(row, render=False):
    meta = row.get('metadata') or {}
    state = row.get('status') if render else meta.get('state', 'queued')
    results = meta.get('results') or []
    scenes = (meta.get('input') or {}).get('scenes') or []
    # Discovery outcomes are not rendered or approved outputs.
    completed = sum(r.get('status') in ('approved', 'reviewed', 'skipped') for r in results)
    if meta.get('kind') == 'ae_speaker_coordinates': completed = len(results)
    if meta.get('kind') in ('motion_automation','effectcraft_automation','horizontal_webtoon_automation','filmcraft_automation'): completed = sum(r.get('review',{}).get('passed') is True for r in results)
    return {'id': row['id'], 'project_id': meta.get('std_web_project_id') or row.get('project_id'),
            'title': row.get('project_name') or '', 'kind': 'render' if render else meta.get('kind'),
            'state': state, 'group': 'review' if meta.get('kind') == 'region_motion_plan' and state == 'ready' else group(state), 'phase': meta.get('phase'), 'error': meta.get('error') or row.get('error_message'), 'message': meta.get('progress') or row.get('message'),
            'total': meta.get('total_scenes') or len(scenes), 'done': completed, 'analyzed': len(results),
            'generated': sum(bool(r.get('asset_id')) and r.get('status') in ('review_pending', 'approved', 'reviewed') for r in results),
            'skipped': sum(r.get('status') == 'skipped' for r in results),
            'scene_number': row.get('scene_number'),
            'progress': max(0, min(100, float(row.get('progress') or 0))) if render else None,
            'created_at': row.get('created_at'), 'updated_at': row.get('updated_at'),
            'scene_numbers': [r.get('number') for r in results if r.get('status') == 'needs_review']}

def fetch_jobs():
    import requests
    base = (os.getenv('NEXT_PUBLIC_SUPABASE_URL') or os.getenv('SUPABASE_URL') or '').rstrip('/')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not base or not key: raise RuntimeError('Missing database configuration')
    def query(table, params):
        response = query_session().get(base+'/rest/v1/'+table, headers={'apikey':key,'Authorization':'Bearer '+key},
                                params=params, timeout=(5,15))
        response.raise_for_status()
        return response.json()
    # Project only display fields; do not retrieve asset URLs, credentials or full input.
    select = 'id,project_id,scene_number,created_at,updated_at,metadata:metadata->state,kind:metadata->kind,phase:metadata->phase,results:metadata->results,scenes:metadata->input->scenes,total_scenes:metadata->total_scenes,error:metadata->error,progress:metadata->progress'
    # Input scenes can contain assets; select just counts on the server and never return them.
    from worker.workflow_roles import POSTPRODUCTION, asset_query, belongs
    assets = query('std_project_assets', asset_query(POSTPRODUCTION, {'select':select+',preview_sync:metadata->preview_sync,task:metadata->input->task','metadata->>kind':'in.(ae_mouth_job,region_motion_plan,motion_preview,motion_automation,effectcraft_automation,horizontal_webtoon_automation,filmcraft_automation)', 'order':'created_at.desc','limit':'100'}))
    jobs = []
    for row in assets:
        row['metadata'] = {'state':row.get('metadata'), 'kind':row.get('kind'), 'phase':row.get('phase'),
                           'results':row.get('results'), 'error':row.get('error'), 'progress':row.get('progress'), 'preview_sync':row.get('preview_sync'), 'total_scenes':row.get('total_scenes'), 'input':{'scenes':row.get('scenes'),'task':row.get('task')}}
        if not belongs(row,POSTPRODUCTION):continue
        jobs.append(summarize(row))
    renders = query('remote_render_queue', {'select':'id,project_id,project_name,status,progress,message,error_message,created_at,updated_at,web_id:metadata->std_web_project_id',
                                           'render_mode':'eq.gcs_api','order':'created_at.desc','limit':'100'})
    for row in renders:
        row['metadata'] = {'std_web_project_id':row.get('web_id')}
        jobs.append(summarize(row, True))
    ids = sorted({j['project_id'] for j in jobs if j['project_id'] and len(str(j['project_id'])) == 36})
    titles = {p['id']:p for p in query('std_projects', {'select':'id,title,topic_queue_id,source_titles:source_payload->title_translations,project_titles:project_payload->title_translations','id':'in.('+','.join(ids)+')','submitted_at':'not.is.null','status':'not.in.(approved,canceled,cancelled,completed,paid)'})} if ids else {}
    jobs=[job for job in jobs if job['project_id'] in titles]
    topic_ids = sorted({str(p['topic_queue_id']) for p in titles.values() if p.get('topic_queue_id') is not None})
    topics = {str(t['id']):t for t in query('topics_queue', {'select':'id,progress_titles:progress_payload->title_translations,structure_titles:pregenerated_structure->title_translations,metadata_titles:publish_metadata->title_translations','id':'in.('+','.join(topic_ids)+')'})} if topic_ids else {}
    for job in jobs:
        project = titles[job['project_id']]
        job['title'] = project.get('title') or job['title'] or '이름 없는 프로젝트'
        job['topic_queue_id'] = project.get('topic_queue_id')
        # The projections above are translation dictionaries, not full project payloads.
        project = {**project, 'source_titles':{'title_translations':project.get('source_titles')}, 'project_titles':{'title_translations':project.get('project_titles')}}
        job['title_ko'] = korean_title(project, topics.get(str(job['topic_queue_id'])))
    return sorted(jobs, key=lambda j:j['created_at'] or '', reverse=True)

class Snapshot:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = {'jobs':[], 'updated_at':None, 'error':None}
        self.next_poll = 0
    def read(self):
        with self.lock:
            if time.monotonic() >= self.next_poll:
                self.next_poll = time.monotonic()+15
                try:
                    self.value = {'jobs':fetch_jobs(), 'updated_at':datetime.now(timezone.utc).isoformat(), 'error':None}
                except Exception as error:
                    self.value = {**self.value, 'error':type(error).__name__}
            return dict(self.value)
