"""Read-only, bounded queue summary for the loopback worker dashboard."""
import os
import threading
import time
from datetime import datetime, timezone

def group(state):
    if state in ('ready', 'reviewed', 'completed'): return 'completed'
    if state in ('failed', 'obsolete', 'cancelled'): return 'failed'
    if state in ('prepared', 'approved', 'needs_review', 'direction_pending', 'review_pending'): return 'review'
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
    return {'id': row['id'], 'project_id': meta.get('std_web_project_id') or row.get('project_id'),
            'title': row.get('project_name') or '', 'kind': 'render' if render else meta.get('kind'),
            'state': state, 'group': 'review' if meta.get('kind') == 'region_motion_plan' and state == 'ready' else group(state), 'phase': meta.get('phase'),
            'total': len(scenes), 'done': completed, 'analyzed': len(results),
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
        response = requests.get(base+'/rest/v1/'+table, headers={'apikey':key,'Authorization':'Bearer '+key},
                                params=params, timeout=(5,15))
        response.raise_for_status()
        return response.json()
    # Project only display fields; do not retrieve asset URLs, credentials or full input.
    select = 'id,project_id,scene_number,created_at,updated_at,metadata:metadata->state,kind:metadata->kind,phase:metadata->phase,results:metadata->results,scenes:metadata->input->scenes'
    # Input scenes can contain assets; select just counts on the server and never return them.
    assets = query('std_project_assets', {'select':select,'metadata->>kind':'in.(ae_speaker_coordinates,ae_mouth_job,region_layer_package,region_motion_plan)', 'order':'created_at.desc','limit':'100'})
    jobs = []
    for row in assets:
        row['metadata'] = {'state':row.get('metadata'), 'kind':row.get('kind'), 'phase':row.get('phase'),
                           'results':row.get('results'), 'input':{'scenes':row.get('scenes')}}
        jobs.append(summarize(row))
    renders = query('remote_render_queue', {'select':'id,project_id,project_name,status,progress,created_at,updated_at,web_id:metadata->std_web_project_id',
                                           'render_mode':'eq.gcs_api','order':'created_at.desc','limit':'100'})
    for row in renders:
        row['metadata'] = {'std_web_project_id':row.get('web_id')}
        jobs.append(summarize(row, True))
    ids = sorted({j['project_id'] for j in jobs if j['project_id'] and len(str(j['project_id'])) == 36})
    titles = {p['id']:p.get('title') for p in query('std_projects', {'select':'id,title','id':'in.('+','.join(ids)+')'})} if ids else {}
    for job in jobs: job['title'] = titles.get(job['project_id']) or job['title'] or '이름 없는 프로젝트'
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
