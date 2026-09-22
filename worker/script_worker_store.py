"""Server-only persistence for the independent script worker.

Legacy queues are read-only. No renderer/manager imports or queue claims.
"""
import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from worker.script_worker_media import media_summary, unknown_media, thumbnail

TABLE = 'script_worker_jobs'
LEGACY_TYPES = ('codex_content_generate', 'script_generate', 'script_plan_generate')
HISTORY_TYPES = ('new', 'repair', 'grounded', 'topics') + LEGACY_TYPES
HISTORY_FILTER = 'in.(' + ','.join(HISTORY_TYPES) + ')'


class StoreUnavailable(RuntimeError):
    pass


class ScriptStore:
    def __init__(self):
        self._stats = None
        self._stats_at = 0

    def request(self, method, table, *, params=None, body=None, prefer='count=exact'):
        url = (os.getenv('NEXT_PUBLIC_SUPABASE_URL') or os.getenv('SUPABASE_URL') or '').rstrip('/')
        key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        if not url or not key:
            raise StoreUnavailable('Database 연결 설정이 없습니다.')
        try:
            # Fixed-ID upserts are idempotent even if the response is lost.
            for attempt in range(2):
                try:
                    response = requests.request(method, f'{url}/rest/v1/{table}', params=params,
                        json=body, headers={'apikey': key, 'Authorization': f'Bearer {key}',
                                            'Prefer': prefer}, timeout=15)
                    break
                except requests.ConnectionError:
                    if attempt:
                        raise
            if response.status_code == 409:
                raise StoreUnavailable('다른 대본 작업이 실행 중이거나 저장 버전이 충돌했습니다.')
            response.raise_for_status()
            count = response.headers.get('Content-Range', '').split('/')[-1]
            return (response.json() if response.content else []), int(count) if count.isdigit() else None
        except (requests.RequestException, ValueError) as exc:
            raise StoreUnavailable('Database 읽기/저장 실패. 연결을 확인한 뒤 다시 시도하세요.') from exc

    def save(self, bundle):
        job = dict(bundle['job'])
        job.pop('sync_error', None)
        job.pop('sync_status', None)
        row = {'id': job['id'], 'title': job['title'], 'mode': job['mode'],
               'status': job['status'], 'worker_id': job.get('worker_id', ''),
               'created_at': job['created_at'], 'updated_at': job['updated_at'],
               'job_record': job, 'request_data': bundle.get('request', {}),
               'source_snapshot': bundle.get('source', {}),
               'candidate': bundle.get('candidate', {}), 'reference_sources': bundle.get('references', [])}
        self.request('POST', TABLE, params={'on_conflict': 'id'}, body=row,
                     prefer='resolution=merge-duplicates,return=minimal')
        self._stats_at = 0

    def stats(self):
        if self._stats is not None and time.monotonic() - self._stats_at < 15:
            return dict(self._stats)
        _, total = self.request('GET', 'script_worker_history', params={'select': 'id', 'limit': 1, 'job_type': HISTORY_FILTER})
        _, approvals = self.request('GET', TABLE, params={'select': 'id', 'status': 'eq.awaiting_approval', 'limit': 1})
        active = self.active()
        self._stats = {'total': total, 'approvals': approvals, 'active': len(active)}
        self._stats_at = time.monotonic()
        return dict(self._stats)

    def get(self, identity):
        if not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('잘못된 작업 ID입니다.')
        rows, _ = self.request('GET', TABLE, params={'select': '*', 'id': f'eq.{identity}'})
        if not rows:
            raise ValueError('저장된 작업을 찾지 못했습니다.')
        row = rows[0]
        return {'job': row['job_record'], 'request': row['request_data'],
                'source': row['source_snapshot'], 'candidate': row['candidate'],
                'references': row['reference_sources']}

    def active(self):
        rows, _ = self.request('GET', TABLE, params={'select': 'id,worker_id,job_record',
            'status': 'in.(queued,running)'})
        return rows

    def history(self, page=0, origin='all', q='', state='all'):
        params = {'select': '*', 'order': 'created_at.desc,id.desc', 'offset': page * 40, 'limit': 40,
                  'job_type': HISTORY_FILTER}
        if origin != 'all':
            params['origin'] = f'eq.{origin}'
        if state != 'all':
            params['status'] = f'eq.{state}'
        if q.strip():
            safe = q.strip().replace('\\', '\\\\').replace('"', '\\"').replace('*', '').replace('%', '').replace('_', '')
            params['title'] = f'ilike."*{safe}*"'
        rows, count = self.request('GET', 'script_worker_history', params=params)
        self.enrich_media(rows)
        return {'items': rows, 'total': count, 'page': page,
                'has_more': len(rows) == 40 if count is None else (page + 1) * 40 < count}

    def enrich_media(self, rows):
        topics = {str(r.get('source_id')) for r in rows if r['origin'] == 'legacy' and r.get('source_kind') == 'topic' and re.fullmatch(r'\d{1,16}', str(r.get('source_id') or ''))}
        projects = {str(r.get('source_id')) for r in rows if r['origin'] == 'legacy' and r.get('source_kind') == 'project' and re.fullmatch(r'[a-fA-F0-9-]{36}', str(r.get('source_id') or ''))}
        dedicated = {r['id'] for r in rows if r['origin'] == 'dedicated' and re.fullmatch(r'[a-f0-9]{32}', r['id'])}
        queries = {}
        if topics:
            where = 'in.(' + ','.join(sorted(topics)) + ')'
            queries['topics'] = ('topics_queue', {'select': 'id,pregenerated_structure,progress_payload', 'id': where})
            queries['characters'] = ('topic_character_assets', {'select': 'topic_queue_id,character_key,name,image_url', 'topic_queue_id': where, 'limit': 1000})
        if topics or projects:
            clauses = []
            if topics:
                clauses.append('topic_queue_id.in.(' + ','.join(sorted(topics)) + ')')
            if projects:
                clauses.append('id.in.(' + ','.join(sorted(projects)) + ')')
            queries['projects'] = ('std_projects', {'select': 'id,title,topic_queue_id,project_payload,progress_payload', 'or': '(' + ','.join(clauses) + ')', 'order': 'updated_at.desc', 'limit': 1000})
        if dedicated:
            queries['dedicated'] = (TABLE, {'select': 'id,candidate', 'id': 'in.(' + ','.join(sorted(dedicated)) + ')'})
        results, failed = {}, set()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {name: pool.submit(self.request, 'GET', table, params=params) for name, (table, params) in queries.items()}
            for name, future in futures.items():
                try:
                    results[name] = future.result()[0]
                except StoreUnavailable:
                    results[name] = []
                    failed.add(name)
        topic_map = {str(r['id']): r for r in results.get('topics', [])}
        project_map = {str(r['id']): r for r in results.get('projects', [])}
        candidates = {r['id']: r.get('candidate') or {} for r in results.get('dedicated', [])}
        for row in rows:
            sid = str(row.get('source_id') or '')
            row['media'] = unknown_media('미디어 조회 실패' if failed else '연결 자료 없음')
            if row['origin'] == 'dedicated' and row['id'] in candidates:
                row['media'] = media_summary(candidates[row['id']])
                row['media']['basis'] = '이 작업의 생성 결과 · 저장된 이미지 링크 기준'
            elif row.get('source_kind') == 'topic' and sid in topic_map:
                topic = topic_map[sid]
                registry = [r for r in results.get('characters', []) if str(r['topic_queue_id']) == sid]
                row['media'] = media_summary(topic, topic.get('progress_payload'), registry, registry_available='characters' not in failed)
                row['media']['basis'] = '현재 토픽 연결 자료 · 저장된 이미지 링크 기준'
                if not row['media']['thumbnail']['url']:
                    for project in results.get('projects', []):
                        if str(project.get('topic_queue_id')) != sid:
                            continue
                        thumb = thumbnail(project.get('project_payload'), project.get('progress_payload'))
                        if thumb['url']:
                            thumb['label'] = '연결 프로젝트 · ' + thumb['label']
                            row['media']['thumbnail'] = thumb
                            break
                    if not row['media']['thumbnail']['url'] and 'projects' in failed:
                        row['media']['thumbnail']['label'] = '썸네일 조회 실패'
            elif row.get('source_kind') == 'project' and sid in project_map:
                project = project_map[sid]
                row['media'] = media_summary(project.get('project_payload'), project.get('progress_payload'))
                row['media']['basis'] = '현재 프로젝트 연결 자료 · 저장된 이미지 링크 기준'
                if row['title'] == row['job_type']:
                    row['title'] = project.get('title') or row['title']

    def legacy(self, identity):
        import uuid
        uuid.UUID(identity)
        rows, _ = self.request('GET', 'remote_hermes_queue', params={'select': '*',
            'id': f'eq.{identity}', 'job_type': 'in.(' + ','.join(LEGACY_TYPES) + ')'})
        if not rows:
            raise ValueError('기존 대본 작업을 찾지 못했습니다.')
        return rows[0]
