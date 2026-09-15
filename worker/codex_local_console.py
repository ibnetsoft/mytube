"""Dedicated loopback Codex console. No legacy manager/dashboard dependency.

Database access here is read-only. Runs produce local candidates, not silent
production repairs. Browser approval records an exact hash; publication is a
separate, scoped repair operation after media dependencies have been checked.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
from dotenv import load_dotenv
for env_path in (ROOT / '.env', ROOT / '.env.local', ROOT / 'auth-web/.env.local'):
    load_dotenv(env_path, override=False)

PORT = 3003
ORIGIN = f'http://127.0.0.1:{PORT}'
TOKEN = secrets.token_urlsafe(32)
OUT = ROOT / 'output/codex-local-console'
ASSETS = ROOT / 'worker/codex_console'
DOCS = {'repair': ROOT / 'docs/리페어프로세스.md', 'new': ROOT / 'docs/신규생성프로세스.md'}
app = FastAPI(title='AIR Codex Local Worker', docs_url=None, redoc_url=None, openapi_url=None)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


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
    def __init__(self, root):
        self.root = root
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.rows = {}
        for path in root.glob('*/job.json'):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                if item['status'] in ('queued', 'running'):
                    item.update(status='interrupted', stage='서버 재시작: 자동 재실행하지 않음')
                    write_json(path, item)
                self.rows[item['id']] = item
            except (ValueError, KeyError):
                continue

    def update(self, identity, **fields):
        with self.lock:
            self.rows[identity].update(fields, updated_at=time.time())
            write_json(self.root / identity / 'job.json', self.rows[identity])

    def listing(self):
        with self.lock:
            return sorted((dict(r) for r in self.rows.values()), key=lambda r: r['created_at'], reverse=True)

    def start(self, request, snapshot, sources=None):
        with self.lock:
            if any(r['status'] in ('queued', 'running') for r in self.rows.values()):
                raise ValueError('이미 실행 또는 대기 중인 작업이 있습니다. 완료 후 시작하세요.')
            identity = uuid.uuid4().hex
            title = snapshot['summary']['title'] if snapshot else request.title.strip()
            item = {'id': identity, 'mode': request.mode, 'title': title, 'status': 'queued',
                    'stage': '대기', 'created_at': time.time(), 'updated_at': time.time(),
                    'kind': request.kind, 'source_id': request.source_id, 'published': False}
            self.rows[identity] = item
            write_json(self.root / identity / 'job.json', item)
            write_json(self.root / identity / 'request.json', request.model_dump())
            if snapshot:
                write_json(self.root / identity / 'source.json', snapshot)
            if sources:
                write_json(self.root / identity / 'references.json', sources)
            self.pool.submit(self.run, identity, request, snapshot)
            return dict(item)

    def run(self, identity, request, snapshot):
        try:
            self.update(identity, status='running', stage='Codex 준비')
            from worker.codex_local_workflow import produce
            candidate = produce(identity, request.model_dump(), snapshot, self.root / identity,
                                lambda stage: self.update(identity, stage=stage),
                                sources=json.loads((self.root / identity / 'references.json').read_text(encoding='utf-8'))
                                if (self.root / identity / 'references.json').exists() else None)
            write_json(self.root / identity / 'candidate.json', candidate)
            (self.root / identity / 'candidate.md').write_text(candidate['script'], encoding='utf-8')
            self.update(identity, status='awaiting_approval', stage='초안 저장 · 검토 대기',
                        candidate_hash=digest(candidate), remaining=candidate.get('remaining', []))
        except Exception as exc:
            # Do not expose HTTP URLs, credentials, CLI stdout or source dumps to browser logs.
            self.update(identity, status='failed', stage=f'생성 중단 ({type(exc).__name__})',
                        error='검수 또는 실행 실패. 원본은 변경되지 않았습니다. 로컬 단계 산출물을 확인하세요.')

    def approve(self, identity, expected_hash, current_source=None):
        with self.lock:
            item = self.rows.get(identity)
            if not item or item['status'] != 'awaiting_approval':
                raise ValueError('승인 대기 작업이 아닙니다.')
            candidate = json.loads((self.root / identity / 'candidate.json').read_text(encoding='utf-8'))
            if digest(candidate) != expected_hash or item['candidate_hash'] != expected_hash:
                raise ValueError('수정안 버전이 달라졌습니다. 다시 확인하세요.')
            path = self.root / identity / 'source.json'
            if path.exists():
                original = json.loads(path.read_text(encoding='utf-8'))
                if not current_source or original['fingerprint'] != current_source['fingerprint']:
                    raise ValueError('원본이 변경됐습니다. 기존 수정안을 바로 승인할 수 없습니다.')
            self.update(identity, status='approved_pending_repair', stage='승인 기록 · 연관 자료 검증/적용 대기',
                        approved_at=time.time(), approved_hash=expected_hash)


jobs = Jobs(OUT)


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
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.get('/')
def index():
    return HTMLResponse((ASSETS / 'index.html').read_text(encoding='utf-8').replace('__LOCAL_TOKEN__', TOKEN))


@app.get('/assets/{name}')
def asset(name: str):
    if name not in ('app.js', 'style.css', 'grounded.js'):
        raise HTTPException(404)
    return FileResponse(ASSETS / name)


@app.get('/health')
def health():
    return {'service': 'codex-local-console', 'port': PORT, 'legacy_dashboard': False}


@app.get('/api/status')
def status():
    return {'jobs': jobs.listing(), 'codex_installed': bool(shutil.which(os.environ.get('CODEX_EXECUTABLE', 'codex'))),
            'script_model': 'gpt-6-astra', 'output': str(OUT), 'server': '로컬 전용 · 레거시 큐 미사용',
            'login_status': '미확인 — CLI 설치 확인은 로그인/실행 성공을 보장하지 않습니다.'}


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
    if request.mode not in ('new', 'repair', 'grounded'):
        raise HTTPException(400, '모드를 선택하세요.')
    snapshot = None
    references = None
    try:
        if request.mode == 'repair':
            snapshot = source(request.kind, request.source_id)
            if not snapshot['script'] or not snapshot['structure'].get('scenes'):
                raise ValueError('대본 또는 장면 구조가 없어 자동 수정안을 만들 수 없습니다.')
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
    except Exception:
        raise HTTPException(502, '작업 준비 실패. 원본은 변경되지 않았습니다.')


@app.get('/api/jobs/{identity}')
def detail(identity: str):
    if identity not in jobs.rows:
        raise HTTPException(404)
    directory = OUT / identity
    candidate_path = directory / 'candidate.json'
    snapshot_path = directory / 'source.json'
    candidate = json.loads(candidate_path.read_text(encoding='utf-8')) if candidate_path.exists() else {}
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8')) if snapshot_path.exists() else {}
    return {'job': dict(jobs.rows[identity]), 'script': candidate.get('script', ''),
            'original': snapshot.get('script', ''), 'remaining': candidate.get('remaining', []),
            'citations': candidate.get('sections', []) if candidate.get('source_manifest') else [],
            'sources': candidate.get('source_manifest', []), 'grounding_report': candidate.get('grounding_report')}


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
    item = jobs.rows.get(identity)
    if not item:
        raise HTTPException(404)
    try:
        current = source(item['kind'], item['source_id']) if item['mode'] == 'repair' else None
        jobs.approve(identity, request.candidate_hash, current)
        return {'status': 'approved_pending_repair', 'published': False}
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except Exception:
        raise HTTPException(502, '원본 재확인 실패. 승인하거나 덮어쓰지 않았습니다.')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=PORT, access_log=False)
