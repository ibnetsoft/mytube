"""Narrow, authenticated loopback adapter for the native production settings UI."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import tempfile
import time
from urllib.parse import parse_qs, urlsplit, urlencode

ROOT = Path(__file__).resolve().parents[1]
TOKEN = secrets.token_urlsafe(32)
_slots = threading.BoundedSemaphore(3)
_sessions = {}  # Session tokens stay server-side; passwords are never retained.
_uploads = {}

def invoke(path, method='GET', body=None, project_id='', byte_range=None, worker_role='postproduction'):
    with _slots:
        result = subprocess.run([shutil.which('node') or 'node', str(ROOT/'scripts/local_worker_settings.cjs')],
            input=json.dumps({'path':path,'method':method,'body':body,'project_id':project_id,'range':byte_range,'session_token':_sessions.get(project_id,''),'worker_role':worker_role}),
            capture_output=True,text=True,encoding='utf-8',cwd=ROOT,timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for line in reversed(result.stdout.splitlines()):
        if line.startswith('AIR_RESULT:'):
            value=json.loads(line[len('AIR_RESULT:'):])
            session=value.pop('session_token',None)
            if session:_sessions[project_id]=session
            return value
    raise RuntimeError('제작 설정 처리에 실패했습니다. 로컬 Node 실행 환경을 확인하세요.')

def media_urls(value, project_id, token=TOKEN):
    if isinstance(value,dict):return {k:media_urls(v,project_id,token) for k,v in value.items()}
    if isinstance(value,list):return [media_urls(v,project_id,token) for v in value]
    if isinstance(value,str) and value.startswith('/api/std/') and ('/assets/file?' in value or '/assets/gcs-file?' in value):
        return value+'&'+urlencode({'local_token':token,'local_project':project_id})
    return value

def upload_result(result, body, token=TOKEN):
    data=result.get('data') or {}
    if result['status']==200 and data.get('storage_upload_url'):
        target=urlsplit(data['storage_upload_url'])
        if target.scheme!='https' or target.hostname!='storage.googleapis.com':raise ValueError('Unsupported upload storage')
        for key,value in list(_uploads.items()):
            if value['expires']<time.monotonic():_uploads.pop(key,None)
        ticket=secrets.token_urlsafe(32)
        _uploads[ticket]={'url':data['storage_upload_url'],'size':int(body['file_size']),'mime':body['mime_type'],'expires':time.monotonic()+900,'token':token}
        data['storage_upload_url']='/api/local/uploads/'+ticket+'?'+urlencode({'local_token':token})
    return result

def handle(handler):
    """Host and Origin are checked by the enclosing loopback server."""
    url=urlsplit(handler.path)
    if url.path in ('/production-settings.js','/production-settings.css') and handler.command=='GET':
        file=ROOT/'worker/local_production_ui'/url.path.lstrip('/')
        if not file.exists():handler.send_error(503,'Local production UI has not been built');return True
        content='text/javascript' if file.suffix=='.js' else 'text/css'
        handler.send_response(200);handler.send_header('Content-Type',content);handler.end_headers();handler.wfile.write(file.read_bytes());return True
    if url.path=='/fonts/NanumSquareExtraBold.ttf' and handler.command=='GET':
        file=ROOT/'auth-web/public/fonts/NanumSquareExtraBold.ttf'
        if not file.exists():handler.send_error(404);return True
        handler.send_response(200);handler.send_header('Content-Type','font/ttf');handler.end_headers();handler.wfile.write(file.read_bytes());return True
    if not url.path.startswith('/api/'):return False
    query=parse_qs(url.query)
    media=handler.command=='GET' and ('/assets/file' in url.path or url.path=='/api/std/assets/gcs-file')
    upload=handler.command=='PUT' and url.path.startswith('/api/local/uploads/')
    token=handler.headers.get('X-Codex-Local','') or (query.get('local_token',[''])[0] if media or upload else '')
    if not secrets.compare_digest(token,TOKEN):handler.send_error(401,'Refresh the local worker');return True
    project_id=handler.headers.get('X-Local-Project','') or query.get('local_project',[''])[0]
    try:
        if upload:
            ticket=_uploads.pop(url.path.rsplit('/',1)[-1],None)
            size=int(handler.headers.get('Content-Length','0'))
            if not ticket or ticket['expires']<time.monotonic() or size!=ticket['size'] or not 0<size<=1024**3:
                handler.send_error(400,'Upload expired or file size changed');return True
            directory=ROOT/'output/local-worker-uploads';directory.mkdir(parents=True,exist_ok=True)
            filename=None
            try:
                with tempfile.NamedTemporaryFile(dir=directory,delete=False) as stream:
                    filename=Path(stream.name);remaining=size;handler.connection.settimeout(90)
                    while remaining:
                        chunk=handler.rfile.read(min(1024**2,remaining))
                        if not chunk:raise ValueError('Incomplete upload')
                        stream.write(chunk);remaining-=len(chunk)
                import requests
                with filename.open('rb') as stream:
                    response=requests.put(ticket['url'],data=stream,headers={'Content-Type':ticket['mime']},timeout=(10,180),allow_redirects=False)
                handler.send_response(200 if response.ok else 502);handler.end_headers()
            finally:
                if filename:filename.unlink(missing_ok=True)
            return True
        body=None
        if handler.command=='POST':
            size=int(handler.headers.get('Content-Length','0'))
            if size<1 or size>2*1024*1024:handler.send_error(413);return True
            body=json.loads(handler.rfile.read(size))
        result=invoke(handler.path,handler.command,body,project_id,handler.headers.get('Range'))
        # Browser uploads stay on loopback; signed storage URLs are consumed only
        # by the local backend, so bucket CORS need not trust a localhost origin.
        if url.path.endswith('/assets/init') and result['status']==200 and result.get('data',{}).get('storage_upload_url'):
            upload_result(result,body)
        file=None
        try:
            if result.get('file'):
                file=Path(result['file']).resolve()
                if not file.is_relative_to((ROOT/'output/local-worker-api').resolve()):raise ValueError('Invalid media file')
            payload=json.dumps(media_urls(result.get('data'),project_id),ensure_ascii=False).encode('utf-8')
            handler.send_response(result['status']);handler.send_header('Cache-Control','no-store');handler.send_header('X-Content-Type-Options','nosniff')
            if result.get('redirect'):handler.send_header('Location',result['redirect'])
            elif file:
                for key,value in result.get('headers',{}).items():handler.send_header(key,value)
            else:handler.send_header('Content-Type','application/json; charset=utf-8')
            handler.end_headers()
            if file:
                with file.open('rb') as stream:shutil.copyfileobj(stream,handler.wfile)
            elif not result.get('redirect'):handler.wfile.write(payload)
        finally:
            if file:file.unlink(missing_ok=True)
    except (BrokenPipeError,ConnectionResetError):pass
    except Exception:
        payload=json.dumps({'error':'로컬 제작 설정을 처리하지 못했습니다. 잠시 후 다시 시도하세요.'},ensure_ascii=False).encode('utf-8')
        handler.send_response(503);handler.send_header('Content-Type','application/json; charset=utf-8');handler.end_headers();handler.wfile.write(payload)
    return True
