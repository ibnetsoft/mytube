"""Dedicated loopback Codex console. No legacy manager/dashboard dependency.

Database stores requests, progress, results and approvals. Local files are recovery
copies. Existing topic/project scripts are preserved until a scoped publication.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
import socket
from concurrent.futures import ThreadPoolExecutor

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Literal
from worker.script_worker_store import ScriptStore, StoreUnavailable
from worker.script_worker_media import media_summary

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
from dotenv import load_dotenv
for env_path in (ROOT / '.env', ROOT / '.env.local', ROOT / 'auth-web/.env.local'):
    load_dotenv(env_path, override=False)

PORT = 3003
ORIGIN = f'http://127.0.0.1:{PORT}'
TOKEN = secrets.token_urlsafe(32)
OUT = ROOT / 'output/codex-local-console'
WORKER_ID = hashlib.sha256((socket.gethostname() + str(ROOT)).encode()).hexdigest()[:24]
ASSETS = ROOT / 'worker/codex_console'
DOCS = {'repair': ROOT / 'docs/리페어프로세스.md', 'new': ROOT / 'docs/신규생성프로세스.md'}
app = FastAPI(title='AIR AI Local Worker', docs_url=None, redoc_url=None, openapi_url=None)
AE_WORKER_ROLE = 'ae_highlight_worker'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows scanners can briefly hold a just-written recovery file open.
    for attempt in range(5):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.05 * (attempt + 1))


def db_read(table, **params):
    # Fixed internal table/column callers only; no generic SQL/REST proxy.
    url = (os.environ.get('NEXT_PUBLIC_SUPABASE_URL') or os.environ.get('SUPABASE_URL') or '').rstrip('/')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or ''
    if not url or not key:
        raise RuntimeError('Database configuration missing')
    response = requests.get(f'{url}/rest/v1/{table}', params=params, headers={
        'apikey': key, 'Authorization': f'Bearer {key}', 'Prefer': 'count=exact',
    }, timeout=45)
    response.raise_for_status()
    total = response.headers.get('Content-Range', '').split('/')[-1]
    return response.json(), int(total) if total.isdigit() else None


def object_value(value):
    return value if isinstance(value, dict) else {}


def read_ae_state():
    path = ROOT / 'output/codex-local-console/ae_state_unused.json'
    try:
        import worker_config
        path = worker_config.STATE_DIR / 'ae_highlight_worker.json'
    except Exception:
        pass
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        heartbeat = float(data.get('heartbeat_at') or 0)
        data['fresh'] = bool(heartbeat and time.time() - heartbeat < 45)
        if not data['fresh']:
            data['status'] = 'stopped'
            data['pid'] = None
        return data
    except Exception:
        return {}


def ae_console_status(limit=20):
    state = read_ae_state()
    try:
        import ae_highlight_worker
        rows = ae_highlight_worker.fetch_candidate_topics(max(1, min(int(limit), 100)))
        jobs_for_render = ae_highlight_worker._find_scene_jobs(rows, force=False)
        planned = ready = rendering = failed = missing_source = 0
        recent = []
        for row in rows:
            structure = object_value(row.get('pregenerated_structure'))
            scenes = structure.get('scenes') if isinstance(structure.get('scenes'), list) else []
            for index, scene in enumerate(scenes):
                if not isinstance(scene, dict):
                    continue
                effect_plan = object_value(scene.get('ae_effect_plan'))
                motion_plan = object_value(scene.get('ae_motion_plan'))
                plan_kind = 'effect' if effect_plan.get('enabled') else 'motion' if motion_plan.get('enabled') else ''
                plan = effect_plan if plan_kind == 'effect' else motion_plan
                if not plan.get('enabled'):
                    continue
                planned += 1
                metadata = object_value(scene.get('metadata'))
                asset_key = 'ae_motion_asset' if plan_kind == 'motion' else 'ae_effect_asset'
                status_key = 'ae_motion_status' if plan_kind == 'motion' else 'ae_effect_status'
                video_key = 'ae_motion_video_url' if plan_kind == 'motion' else 'ae_video_url'
                ae_asset = object_value(metadata.get(asset_key))
                status = str(ae_asset.get('status') or scene.get(status_key) or 'planned').lower()
                ready += status == 'ready'
                rendering += status == 'rendering'
                failed += status == 'failed'
                missing_source += 0 if ae_highlight_worker._gcs_ref_from_scene(scene) else 1
                if len(recent) < 12:
                    recent.append({
                        'topic_id': str(row.get('id') or ''),
                        'title': row.get('generated_title') or row.get('topic') or str(row.get('id') or ''),
                        'scene_number': scene.get('scene_number') or scene.get('scene_order') or index + 1,
                        'preset': plan.get('preset') or 'wuxia_sword_aura',
                        'plan_kind': plan_kind,
                        'mood': plan.get('mood') or '',
                        'camera': plan.get('camera') or '',
                        'targets': plan.get('targets') if isinstance(plan.get('targets'), list) else [],
                        'status': status,
                        'media_url': ae_asset.get('media_url') or scene.get(video_key) or '',
                        'error': ae_asset.get('error') or '',
                    })
        afterfx = Path(os.environ.get('AE_AFTERFX_PATH') or ae_highlight_worker.DEFAULT_AFTERFX)
        aerender = Path(os.environ.get('AE_AERENDER_PATH') or ae_highlight_worker.DEFAULT_AERENDER)
        return {
            'success': True,
            'state': state,
            'candidate_count': len(jobs_for_render),
            'topics_scanned': len(rows),
            'summary': {'planned': planned, 'ready': ready, 'rendering': rendering,
                        'failed': failed, 'missing_source': missing_source, 'recent': recent},
            'jobs': [{'topic_id': job.topic_id, 'title': job.topic_title, 'scene_number': job.scene_number,
                      'preset': job.preset, 'plan_kind': job.plan_kind, 'duration_seconds': job.duration_seconds,
                      'mood': object_value(job.scene.get('ae_motion_plan' if job.plan_kind == 'motion' else 'ae_effect_plan')).get('mood') or '',
                      'camera': object_value(job.scene.get('ae_motion_plan' if job.plan_kind == 'motion' else 'ae_effect_plan')).get('camera') or '',
                      'targets': object_value(job.scene.get('ae_motion_plan' if job.plan_kind == 'motion' else 'ae_effect_plan')).get('targets') or [],
                      'source': {'bucket': job.source.bucket, 'path': job.source.path}}
                     for job in jobs_for_render[:20]],
            'capability': {'afterfx_path': str(afterfx), 'aerender_path': str(aerender),
                           'afterfx_exists': afterfx.is_file(), 'aerender_exists': aerender.is_file()},
        }
    except Exception as exc:
        return {
            'success': False,
            'state': state,
            'candidate_count': 0,
            'topics_scanned': 0,
            'summary': {'planned': 0, 'ready': 0, 'rendering': 0, 'failed': 0, 'missing_source': 0, 'recent': []},
            'jobs': [],
            'capability': {},
            'error': str(exc),
        }


def start_ae_worker_process():
    state = read_ae_state()
    if state.get('fresh') and state.get('status') not in ('stopped', 'failed'):
        return {'success': True, 'already_running': True, 'pid': state.get('pid')}
    log_path = OUT / 'ae_highlight_worker.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open('a', encoding='utf-8', errors='replace')
    cmd = [sys.executable, str(ROOT / 'worker/ae_highlight_worker.py'), '--loop']
    kwargs = {'cwd': str(ROOT), 'stdin': subprocess.DEVNULL, 'stdout': log_handle, 'stderr': log_handle}
    if sys.platform == 'win32':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
    process = subprocess.Popen(cmd, **kwargs)
    return {'success': True, 'pid': process.pid, 'log_path': str(log_path)}


def summary(row, kind):
    project = kind == 'project'
    payload = object_value(row.get('project_payload')) if project else row
    structure = object_value(payload.get('structure') if project else row.get('pregenerated_structure'))
    scenes = structure.get('scenes') or []
    progress = object_value(row.get('progress_payload'))
    script = payload.get('script') if project else row.get('pregenerated_script')
    return {
        'kind': kind, 'id': str(row['id']), 'topic_id': str(row.get('topic_queue_id') or row['id']),
        'title': row.get('title') or row.get('generated_title') or row.get('topic') or '',
        'owner': row.get('employee_email') or row.get('assigned_employee_email') or '',
        'status': row.get('status'), 'category_id': row.get('category_id') or payload.get('category_id'),
        'has_script': bool(script), 'scenes': len(scenes),
        'image_links': sum(bool(s.get('image_url')) for s in scenes if isinstance(s, dict)),
        'thumbnail': '사용자 저장 완료' if progress.get('thumbnail_completed') else
                     '배경 준비' if progress.get('thumbnail_bg_url') else '미확인',
        'protected': bool(row.get('submitted_at')) or row.get('status') in
            ('review_requested', 'submitted', 'approved', 'completed', 'paid', 'canceled', 'cancelled'),
    }


def source(kind, identity):
    if kind not in ('topic', 'project'):
        raise ValueError('Invalid source kind')
    if kind == 'topic' and (not identity.isdigit() or len(identity) > 16):
        raise ValueError('Invalid topic ID')
    if kind == 'project':
        uuid.UUID(identity)
    rows, _ = db_read('topics_queue' if kind == 'topic' else 'std_projects', select='*', id=f'eq.{identity}')
    if len(rows) != 1:
        raise ValueError('Source not found')
    row = rows[0]
    item = summary(row, kind)
    payload = object_value(row.get('project_payload'))
    structure = object_value(payload.get('structure') if kind == 'project' else row.get('pregenerated_structure'))
    script = (payload.get('script') if kind == 'project' else row.get('pregenerated_script')) or ''
    # Fingerprint includes ownership, submission and all payload changes, not only prose.
    return {'kind': kind, 'id': identity, 'summary': item, 'row': row,
            'structure': structure, 'script': script, 'fingerprint': digest(row)}


class StartRequest(BaseModel):
    mode: str
    kind: str = 'topic'
    source_id: str = Field(default='', max_length=64)
    title: str = Field(default='', max_length=200)
    category: str = Field(default='', max_length=80)
    category_id: str = Field(default='', max_length=16)
    duration_minutes: int = Field(default=15, ge=1, le=60)
    language: Literal['ko', 'en', 'ja', 'es'] = 'ko'
    setting_country: str = Field(default='', max_length=80)
    era_region: str = Field(default='현대 지방 소도시', max_length=120)
    image_style: str = Field(default='실사', max_length=80)
    production_mode: Literal['standard', 'moving_comic'] = 'standard'
    generate_bgm_prompt: bool = Field(default=False, strict=True)
    notes: str = Field(default='', max_length=4000)
    source_ids: list[str] = Field(default_factory=list, max_length=12)
    grounded_type: Literal['sermon', 'education'] = 'sermon'
    audience: str = Field(default='시니어 성도', max_length=200)
    perspective: str = Field(default='', max_length=500)
    passage: str = Field(default='', max_length=200)


class SourceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal['scripture', 'commentary', 'reference']
    locator: str = Field(min_length=1, max_length=300)
    translation: str = Field(default='', max_length=100)
    permission_notes: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=40000)


def load_sources(identities):
    from worker.grounded_script import MAX_PACKET_CHARS
    if not identities or len(set(identities)) != len(identities):
        raise ValueError('중복 없이 자료를 선택하세요.')
    rows = []
    for identity in identities:
        if len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('잘못된 자료 ID입니다.')
        path = OUT / 'sources' / (identity + '.json')
        if not path.is_file():
            raise ValueError('등록 자료를 찾을 수 없습니다.')
        rows.append(json.loads(path.read_text(encoding='utf-8')))
    if sum(len(s['text']) for s in rows) > MAX_PACKET_CHARS:
        raise ValueError('선택 원문은 합계 80,000자 이하로 나눠 작업하세요. 자동 절단하지 않습니다.')
    return rows


class ApproveRequest(BaseModel):
    candidate_hash: str


class Jobs:
    def __init__(self, root, store=None):
        self.root = root
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.rows = {}
        self.store = store
        self.cloud_ready = False
        self.cloud_error = ''
        self.inflight = set()
        for path in root.glob('*/job.json'):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                if item['status'] in ('queued', 'running') and item.get('worker_id', WORKER_ID) == WORKER_ID:
                    item.update(status='interrupted', stage='서버 재시작: 자동 재실행하지 않음', sync_status='pending', updated_at=time.time())
                    write_json(path, item)
                self.rows[item['id']] = item
            except (ValueError, KeyError):
                continue

    def bundle(self, identity):
        def read(name, default):
            path = self.root / identity / (name + '.json')
            return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
        return {'job': dict(self.rows[identity]), 'request': read('request', {}),
                'source': read('source', {}), 'candidate': read('candidate', {}),
                'references': read('references', [])}

    def restore(self, bundle):
        item = dict(bundle['job'])
        identity = item['id']
        # Remote identifiers are validated before they can become local paths.
        if len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('잘못된 작업 ID입니다.')
        for name in ('request', 'source', 'candidate', 'references'):
            write_json(self.root / identity / (name + '.json'), bundle.get(name, [] if name == 'references' else {}))
        item['sync_status'] = 'synced'
        self.rows[identity] = item
        write_json(self.root / identity / 'job.json', item)

    def sync(self, identity, required=False):
        if self.store is None:
            return
        with self.lock:
            item = self.rows[identity]
            try:
                self.store.save(self.bundle(identity))
                item.update(sync_status='synced', sync_error='')
            except StoreUnavailable as exc:
                item.update(sync_status='pending', sync_error=str(exc))
                if required:
                    raise
            finally:
                write_json(self.root / identity / 'job.json', item)

    def connect(self):
        if self.store is None or self.cloud_ready:
            return
        with self.lock:
            if self.cloud_ready:
                return
            try:
                for remote in self.store.active():
                    if remote['worker_id'] == WORKER_ID:
                        identity = remote['id']
                        if identity not in self.rows:
                            self.restore(self.store.get(identity))
                        if self.rows[identity]['status'] in ('queued', 'running'):
                            self.update(identity, status='interrupted', stage='서버 재시작 · 재실행 필요')
                        else:
                            # A completed result may still be waiting for upload.
                            self.sync(identity)
                # Migrate existing local records and retry an interrupted upload.
                for identity in list(self.rows):
                    if self.rows[identity].get('sync_status') != 'synced':
                        self.sync(identity)
                self.cloud_ready = True
                self.cloud_error = ''
            except StoreUnavailable as exc:
                self.cloud_error = str(exc)
                raise

    def load(self, identity):
        with self.lock:
            if self.store and identity not in self.inflight and self.rows.get(identity, {}).get('sync_status') != 'pending':
                self.restore(self.store.get(identity))
            elif identity not in self.rows:
                if not self.store:
                    raise ValueError('작업을 찾지 못했습니다.')
                self.restore(self.store.get(identity))
            return self.bundle(identity)

    def update(self, identity, **fields):
        with self.lock:
            self.rows[identity].update(fields, updated_at=time.time())
            write_json(self.root / identity / 'job.json', self.rows[identity])
            self.sync(identity)

    def listing(self):
        with self.lock:
            return sorted((dict(r) for r in self.rows.values()), key=lambda r: r['created_at'], reverse=True)

    def start(self, request, snapshot, sources=None, retry_of=None):
        with self.lock:
            self.connect()
            if any(r['status'] in ('queued', 'running') for r in self.rows.values()):
                raise ValueError('이미 실행 또는 대기 중인 작업이 있습니다. 완료 후 시작하세요.')
            identity = uuid.uuid4().hex
            title = snapshot['summary']['title'] if snapshot else request.title.strip()
            from worker.content_language import resolve_setting
            setting = resolve_setting(request.model_dump())
            item = {'id': identity, 'mode': request.mode, 'title': title, 'status': 'queued',
                    'stage': '대기', 'created_at': time.time(), 'updated_at': time.time(),
                    'kind': request.kind, 'source_id': request.source_id,
                    'language': setting['language'],
                    'setting_country': setting['setting_country'],
                    'era_region': setting['era_region'],
                    'image_style': setting['image_style'],
                    'content_setting': setting,
                    'published': False, 'worker_id': WORKER_ID, 'retry_of': retry_of}
            self.rows[identity] = item
            write_json(self.root / identity / 'job.json', item)
            write_json(self.root / identity / 'request.json', request.model_dump())
            if snapshot:
                write_json(self.root / identity / 'source.json', snapshot)
            if sources:
                write_json(self.root / identity / 'references.json', sources)
            try:
                self.sync(identity, required=True)
            except StoreUnavailable:
                # No CLI execution when the durable queue reservation failed.
                item.update(status='failed', stage='시작 전 Database 저장 실패', updated_at=time.time())
                write_json(self.root / identity / 'job.json', item)
                raise
            self.inflight.add(identity)
            self.pool.submit(self.run, identity, request, snapshot)
            return dict(item)

    def run(self, identity, request, snapshot):
        try:
            self.update(identity, status='running', stage='AI 준비')
            from worker.codex_local_workflow import produce
            candidate = produce(identity, request.model_dump(), snapshot, self.root / identity,
                                lambda stage: self.update(identity, stage=stage),
                                sources=json.loads((self.root / identity / 'references.json').read_text(encoding='utf-8'))
                                if (self.root / identity / 'references.json').exists() else None)
            write_json(self.root / identity / 'candidate.json', candidate)
            if candidate.get('sfx_plan'):
                write_json(self.root / identity / 'sfx-plan.json', candidate['sfx_plan'])
            (self.root / identity / 'candidate.md').write_text(candidate['script'], encoding='utf-8')
            self.update(identity, status='completed' if request.mode == 'topics' else 'awaiting_approval',
                        stage='토픽 후보 저장 · 선택 가능' if request.mode == 'topics' else '초안 저장 · 검토 대기',
                        candidate_hash=digest(candidate), remaining=candidate.get('remaining', []))
        except Exception as exc:
            # Do not expose HTTP URLs, credentials, CLI stdout or source dumps to browser logs.
            self.update(identity, status='failed', stage=f'생성 중단 ({type(exc).__name__})',
                        error='검수 또는 실행 실패. 원본은 변경되지 않았습니다. 로컬 단계 산출물을 확인하세요.')
        finally:
            with self.lock:
                self.inflight.discard(identity)

    def approve(self, identity, expected_hash, current_source=None):
        with self.lock:
            item = self.rows.get(identity)
            if not item or item['status'] != 'awaiting_approval':
                raise ValueError('승인 대기 작업이 아닙니다.')
            candidate = json.loads((self.root / identity / 'candidate.json').read_text(encoding='utf-8'))
            if digest(candidate) != expected_hash or item['candidate_hash'] != expected_hash:
                raise ValueError('수정안 버전이 달라졌습니다. 다시 확인하세요.')
            path = self.root / identity / 'source.json'
            if path.exists() and json.loads(path.read_text(encoding='utf-8')):
                original = json.loads(path.read_text(encoding='utf-8'))
                if not current_source or original['fingerprint'] != current_source['fingerprint']:
                    raise ValueError('원본이 변경됐습니다. 기존 수정안을 바로 승인할 수 없습니다.')
            self.update(identity, status='approved_pending_repair', stage='승인 기록 · 연관 자료 검증/적용 대기',
                        approved_at=time.time(), approved_hash=expected_hash)
            if self.store and self.rows[identity].get('sync_status') != 'synced':
                raise StoreUnavailable('승인은 로컬에 보관됐지만 Database 저장이 지연됐습니다. 재동기화하세요.')


store = ScriptStore()
jobs = Jobs(OUT, store)


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    if request.headers.get('host') != f'127.0.0.1:{PORT}':
        return JSONResponse({'error': 'Loopback host required'}, status_code=403)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return JSONResponse({'error': 'Cross-site request denied'}, status_code=403)
    origin = request.headers.get('origin')
    if origin and origin != ORIGIN:
        return JSONResponse({'error': 'Origin denied'}, status_code=403)
    if request.url.path.startswith('/api/') and not secrets.compare_digest(request.headers.get('x-codex-local', ''), TOKEN):
        return JSONResponse({'error': '로컬 화면을 새로고침하세요.'}, status_code=401)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data: https:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.get('/')
def index():
    return HTMLResponse((ASSETS / 'index.html').read_text(encoding='utf-8').replace('__LOCAL_TOKEN__', TOKEN))


@app.get('/assets/{name}')
def asset(name: str):
    if name not in ('app.js', 'style.css', 'grounded.js', 'topics.js', 'management.js', 'refresh.js'):
        raise HTTPException(404)
    return FileResponse(ASSETS / name)


@app.get('/health')
def health():
    return {'service': 'codex-local-console', 'port': PORT, 'legacy_dashboard': False}


@app.get('/api/status')
def status():
    cloud_summary = None
    storage_error = ''
    try:
        jobs.connect()
        if jobs.store:
            cloud_summary = jobs.store.stats()
    except StoreUnavailable as exc:
        storage_error = str(exc)
    return {'jobs': jobs.listing(), 'codex_installed': bool(shutil.which(os.environ.get('CODEX_EXECUTABLE', 'codex'))),
            'script_model': 'gpt-6-astra', 'output': str(OUT), 'server': '대본 전용 워커 · Database 저장',
            'cloud_summary': cloud_summary,
            'storage': {'connected': jobs.cloud_ready and not storage_error, 'error': storage_error or jobs.cloud_error,
                        'pending': sum(r.get('sync_status') == 'pending' for r in jobs.rows.values())},
            'login_status': '미확인 — CLI 설치 확인은 로그인/실행 성공을 보장하지 않습니다.'}


@app.get('/api/ae-highlight/status')
def ae_highlight_status(limit: int = 20):
    return ae_console_status(limit)


@app.post('/api/ae-highlight/start')
def ae_highlight_start():
    try:
        return start_ae_worker_process()
    except Exception as exc:
        raise HTTPException(502, f'AE 워커 시작 실패: {exc}')


@app.post('/api/ae-highlight/stop')
def ae_highlight_stop():
    try:
        from shutdown_flag import request_shutdown
        request_shutdown(AE_WORKER_ROLE)
        return {'success': True, 'status': 'shutdown_requested'}
    except Exception as exc:
        raise HTTPException(502, f'AE 워커 중지 요청 실패: {exc}')


@app.get('/api/catalog')
def catalog(kind: str = 'topic', page: int = 0, q: str = ''):
    if kind not in ('topic', 'project') or page < 0 or page > 10000 or len(q) > 200:
        raise HTTPException(400)
    topic = kind == 'topic'
    params = {'select': 'id,topic,generated_title,category_id,status,assigned_employee_email,pregenerated_script,pregenerated_structure,progress_payload' if topic else
              'id,title,status,employee_email,topic_queue_id,submitted_at,project_payload,progress_payload',
              'order': 'id.desc' if topic else 'updated_at.desc', 'offset': page * 40, 'limit': 40}
    if q.strip():
        # Quote reserved PostgREST characters instead of accepting filter syntax.
        safe = q.strip().replace('\\', '\\\\').replace('"', '\\"').replace('*', '').replace('%', '').replace('_', '')
        fields = ['topic', 'generated_title'] if topic else ['title', 'employee_email']
        clauses = [f'{field}.ilike."*{safe}*"' for field in fields]
        if topic and q.isdigit():
            clauses.append(f'id.eq.{int(q)}')
        params['or'] = '(' + ','.join(clauses) + ')'
    try:
        rows, total = db_read('topics_queue' if topic else 'std_projects', **params)
        return {'items': [summary(row, kind) for row in rows], 'total': total, 'page': page,
                'has_more': len(rows) == 40 if total is None else (page + 1) * 40 < total}
    except Exception:
        raise HTTPException(502, '목록을 읽지 못했습니다. DB 연결/설정을 확인하세요. 0건으로 처리하지 않습니다.')


@app.get('/api/categories')
def categories():
    try:
        rows, _ = db_read('categories', select='id,name', order='id', limit=500)
        return {'items': rows}
    except Exception:
        raise HTTPException(502, '카테고리 조회 실패')


@app.get('/api/source/{kind}/{identity}')
def read_source(kind: str, identity: str):
    try:
        result = source(kind, identity)
        return {k: result[k] for k in ('kind', 'id', 'summary', 'script', 'fingerprint')}
    except Exception:
        raise HTTPException(400, '대상 대본 조회에 실패했습니다.')


@app.get('/api/docs/{name}')
def document(name: str):
    if name not in DOCS:
        raise HTTPException(404)
    return {'text': DOCS[name].read_text(encoding='utf-8')}


@app.post('/api/jobs')
def start(request: StartRequest):
    if request.mode not in ('new', 'repair', 'grounded', 'topics'):
        raise HTTPException(400, '모드를 선택하세요.')
    snapshot = None
    references = None
    try:
        if request.mode == 'repair':
            snapshot = source(request.kind, request.source_id)
            if not snapshot['script'] or not snapshot['structure'].get('scenes'):
                raise ValueError('대본 또는 장면 구조가 없어 자동 수정안을 만들 수 없습니다.')
        elif request.mode == 'topics':
            if not request.category.strip():
                raise ValueError('토픽 카테고리를 입력하세요.')
            references = load_sources(request.source_ids)
            request.title = request.title.strip() or references[0]['title'][:180] + ' · 토픽 구성'
        elif request.mode == 'grounded':
            if not request.title.strip() or not request.perspective.strip() or not request.passage.strip():
                raise ValueError('제목·본문 범위·해석 관점을 입력하세요.')
            references = load_sources(request.source_ids)
            if request.grounded_type == 'sermon' and not any(s['kind'] == 'scripture' for s in references):
                raise ValueError('설교에는 성경 원문 자료가 필요합니다.')
        elif not request.title.strip() or not request.category.strip():
            raise ValueError('신규 생성의 제목과 카테고리를 입력하세요.')
        return jobs.start(request, snapshot, references)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except StoreUnavailable as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        raise HTTPException(502, '작업 준비 실패. 원본은 변경되지 않았습니다.')


@app.get('/api/jobs/{identity}')
def detail(identity: str):
    try:
        bundle = jobs.load(identity)
    except ValueError:
        raise HTTPException(404, '작업을 찾지 못했습니다.')
    except StoreUnavailable as exc:
        raise HTTPException(502, str(exc))
    return job_detail(bundle)


def job_detail(bundle):
    candidate = bundle.get('candidate') or {}
    snapshot = bundle.get('source') or {}
    job_row = dict(bundle['job'])
    from worker.content_language import resolve_setting
    content_setting = candidate.get('content_setting') or job_row.get('content_setting')
    if not content_setting and (job_row.get('language') or job_row.get('setting_country')):
        content_setting = resolve_setting(job_row)
    image_stage_info = {
        'status': 'pending_downstream',
        'label': '배경 설정 저장 완료 (실제 이미지 생성은 후속 단계에서 적용)',
        'summary': content_setting.get('summary_label') if content_setting else '',
    }
    return {'job': job_row, 'script': candidate.get('script', ''),
            'content_setting': content_setting, 'image_stage_info': image_stage_info,
            'sfx_summary': {'status': (candidate.get('sfx_plan') or {}).get('status', 'not_run'),
                            'count': len(candidate.get('sfx_cues') or []),
                            'review_count': sum(bool(c.get('needs_review')) for c in candidate.get('sfx_cues') or [])},
            'original': snapshot.get('script', ''), 'remaining': candidate.get('remaining', []),
            'citations': candidate.get('sections', []) if candidate.get('source_manifest') else [],
            'sources': candidate.get('source_manifest', []), 'grounding_report': candidate.get('grounding_report'),
            'topics': candidate.get('topics', []), 'source_analysis': candidate.get('source_analysis'),
            'result_data': candidate, 'result_origin': '전용 워커에 저장된 작업 결과',
            'media': media_summary(candidate),
            'source_link': {'kind': job_row.get('kind'), 'id': job_row.get('source_id')}
                           if job_row.get('source_id') else None}


@app.get('/api/history')
def history(page: int = 0, origin: Literal['all', 'dedicated', 'legacy'] = 'all',
            q: str = '', state: str = 'all'):
    if page < 0 or page > 10000 or len(q) > 200 or state not in (
            'all', 'queued', 'pending', 'running', 'rendering', 'failed', 'interrupted',
            'completed', 'awaiting_approval', 'approved_pending_repair', 'canceled'):
        raise HTTPException(400, '조회 조건을 확인하세요.')
    try:
        return store.history(page, origin, q, state)
    except StoreUnavailable as exc:
        raise HTTPException(502, str(exc))


@app.get('/api/history/legacy/{identity}')
def legacy_detail(identity: str):
    try:
        row = store.legacy(identity)
        payload = object_value(row.get('payload'))
        candidate = object_value(row.get('result_payload'))
        topic_id = str(payload.get('topic_queue_id') or '')
        project_id = str(payload.get('project_id') or '')
        link = {'kind': 'topic', 'id': topic_id} if topic_id.isdigit() else (
            {'kind': 'project', 'id': project_id} if project_id else None)
        result_origin = '기존 작업에 저장된 결과 스냅샷'
        script = candidate.get('script') or ''
        if not script and link:
            try:
                current = source(link['kind'], link['id'])
                script = current['script']
                result_origin = '연결된 대본의 현재 저장본 · 이 작업 당시의 결과 스냅샷이 아닙니다'
            except (ValueError, requests.RequestException, RuntimeError):
                result_origin = '작업 결과 대본 없음 · 연결된 현재 대본도 조회할 수 없습니다'
        elif not script:
            result_origin = '작업에 저장된 대본 없음 · 아래 결과 데이터 확인'
        job = {'id': row['id'], 'origin': 'legacy', 'mode': row['job_type'],
               'title': payload.get('upload_title') or payload.get('topic') or payload.get('title') or row['job_type'],
               'status': row['status'], 'stage': row.get('message') or row.get('worker_status') or '',
               'error': row.get('error_message') or ''}
        result = job_detail({'job': job, 'candidate': candidate})
        result.update(script=script, result_origin=result_origin, source_link=link)
        media_row = {'origin': 'legacy', 'id': identity, 'title': job['title'], 'job_type': row['job_type'],
                     'source_kind': link['kind'] if link else '', 'source_id': link['id'] if link else ''}
        store.enrich_media([media_row])
        result['media'] = media_row['media']
        result['job']['title'] = media_row['title']
        return result
    except ValueError:
        raise HTTPException(404, '기존 작업을 찾지 못했습니다.')
    except StoreUnavailable as exc:
        raise HTTPException(502, str(exc))


@app.post('/api/jobs/{identity}/sync')
def sync_job(identity: str):
    try:
        bundle = jobs.load(identity)
        if bundle['job'].get('sync_status') == 'pending':
            jobs.sync(identity, required=True)
        return {'status': 'synced'}
    except ValueError:
        raise HTTPException(404, '작업을 찾지 못했습니다.')
    except StoreUnavailable as exc:
        raise HTTPException(502, str(exc))


@app.post('/api/jobs/{identity}/retry')
def retry_job(identity: str):
    try:
        bundle = jobs.load(identity)
        if bundle['job']['status'] not in ('failed', 'interrupted'):
            raise ValueError('실패하거나 중단된 작업만 재실행할 수 있습니다.')
        request = StartRequest(**bundle['request'])
        snapshot = bundle['source'] or None
        if request.mode == 'repair':
            current = source(request.kind, request.source_id)
            if not snapshot or snapshot['fingerprint'] != current['fingerprint']:
                raise ValueError('원본이 변경됐습니다. 대본 보관함에서 새 수정 작업을 시작하세요.')
        return jobs.start(request, snapshot, bundle['references'], retry_of=identity)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except StoreUnavailable as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        raise HTTPException(502, '재실행 준비에 실패했습니다. 원본과 연결 상태를 확인하세요.')


class YouTubeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


@app.post('/api/youtube-transcript')
def youtube_transcript(request: YouTubeRequest):
    from worker.youtube_transcript import extract_transcript
    try:
        return extract_transcript(request.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


@app.get('/api/references')
def references():
    rows = [json.loads(p.read_text(encoding='utf-8')) for p in (OUT / 'sources').glob('*.json')]
    return {'items': [{k:v for k,v in row.items() if k != 'text'} | {'characters':len(row['text'])} for row in rows]}


@app.post('/api/references')
def add_reference(request: SourceRequest):
    from worker.grounded_script import validate_source
    try:
        row = validate_source(request.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    row.update(id=uuid.uuid4().hex, created_at=time.time())
    write_json(OUT / 'sources' / (row['id'] + '.json'), row)
    return {'id':row['id'], 'title':row['title'], 'sha256':row['sha256']}


@app.get('/api/references/{identity}')
def reference(identity: str):
    try:
        return load_sources([identity])[0]
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post('/api/jobs/{identity}/approve')
def approve(identity: str, request: ApproveRequest):
    try:
        item = jobs.load(identity)['job']
        current = source(item['kind'], item['source_id']) if item['mode'] == 'repair' else None
        jobs.approve(identity, request.candidate_hash, current)
        return {'status': 'approved_pending_repair', 'published': False}
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except StoreUnavailable as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        raise HTTPException(502, '원본 재확인 실패. 승인하거나 덮어쓰지 않았습니다.')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=PORT, access_log=False)
