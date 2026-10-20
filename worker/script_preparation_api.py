"""Inline pre-submission UI/API for the script console, with its existing token."""
import json
import time
import secrets
import tempfile
from pathlib import Path
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse
from starlette.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from worker import local_production_settings as bridge

def register(app, token):
    async def static_asset(request: Request):
        name=request.url.path.rsplit('/',1)[-1]
        if name not in ('production-settings.js','production-settings.css'):return Response(status_code=404)
        return FileResponse(bridge.ROOT/'worker/local_production_ui'/name,media_type='text/javascript' if name.endswith('.js') else 'text/css')
    for name in ('production-settings.js','production-settings.css'):
        app.add_api_route('/'+name,static_asset,methods=['GET'])
    async def font():
        return FileResponse(bridge.ROOT/'auth-web/public/fonts/NanumSquareExtraBold.ttf',media_type='font/ttf')
    app.add_api_route('/fonts/NanumSquareExtraBold.ttf',font,methods=['GET'])

    async def api(request: Request, resource: str):
        project=request.headers.get('x-local-project','') or request.query_params.get('local_project','')
        if request.method=='PUT':
            ticket=bridge._uploads.pop(request.url.path.rsplit('/',1)[-1],None)
            size=int(request.headers.get('content-length','0'))
            if not ticket or not secrets.compare_digest(ticket.get('token',''),token) or ticket['expires']<time.monotonic() or size!=ticket['size'] or not 0<size<=1024**3:
                return JSONResponse({'error':'업로드 요청을 다시 준비하세요.'},status_code=400)
            directory=bridge.ROOT/'output/local-worker-uploads';directory.mkdir(parents=True,exist_ok=True)
            target=None
            try:
                with tempfile.NamedTemporaryFile(dir=directory,delete=False) as stream:
                    target=Path(stream.name);written=0
                    async for chunk in request.stream():
                        written+=len(chunk)
                        if written>size:raise ValueError('Upload too large')
                        stream.write(chunk)
                if written!=size:raise ValueError('Incomplete upload')
                def send():
                    import requests
                    with target.open('rb') as stream:return requests.put(ticket['url'],data=stream,headers={'Content-Type':ticket['mime']},timeout=(10,180),allow_redirects=False).ok
                ok=await run_in_threadpool(send)
                return Response(status_code=200 if ok else 502)
            finally:
                if target:target.unlink(missing_ok=True)
        try:
            body=None
            if request.method in ('POST','PATCH'):
                raw=await request.body()
                if len(raw)>2*1024**2:return Response(status_code=413)
                body=json.loads(raw)
            result=await run_in_threadpool(bridge.invoke,str(request.url.path)+('?' + request.url.query if request.url.query else ''),request.method,body,project,request.headers.get('range'),'preparation')
            if request.url.path.endswith('/assets/init'):bridge.upload_result(result,body,token)
            if result.get('redirect'):return RedirectResponse(result['redirect'],status_code=result['status'])
            if result.get('file'):
                target=Path(result['file']).resolve()
                if not target.is_relative_to((bridge.ROOT/'output/local-worker-api').resolve()):raise ValueError('Invalid media file')
                return FileResponse(target,status_code=result['status'],headers=result.get('headers'),background=BackgroundTask(target.unlink,missing_ok=True))
            return JSONResponse(bridge.media_urls(result.get('data'),project,token),status_code=result['status'])
        except Exception:
            return JSONResponse({'error':'대본워커의 원본·좌표·연출 준비 요청에 실패했습니다.'},status_code=503)
    app.add_api_route('/api/local/{resource:path}',api,methods=['GET','POST','PUT'])
    app.add_api_route('/api/std/{resource:path}',api,methods=['GET','POST','PATCH'])
