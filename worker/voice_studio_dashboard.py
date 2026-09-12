"""Local Voice Studio endpoints. No cloud requests on page load."""
import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from worker.voice_studio_library import catalog, read_choice, save_choice, config_with_choice, SAMPLE_TEXT, validate_choice
from worker.voice_studio_runner import generate, load_config


def create_router(output_root):
    router = APIRouter(prefix='/api/voice-studio')
    root = Path(output_root) / 'voice_library'
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='voice-studio')
    jobs, lock = {}, threading.Lock()

    def mutation(request):
        # Local dashboard currently has auth disabled. Reject cross-site writes.
        from urllib.parse import urlsplit
        origin = request.headers.get('origin')
        if request.headers.get('x-voice-studio') != '1' or (origin and urlsplit(origin).netloc != request.headers.get('host')):
            raise HTTPException(403, '워커 화면에서 요청해 주세요.')

    def enqueue(key, package, config):
        with lock:
            for jid, job in jobs.items():
                if job['key'] == key and job['status'] in ('queued', 'generating'):
                    return {'id': jid, **job}
            if any(job['status'] in ('queued', 'generating') for job in jobs.values()):
                raise HTTPException(409, '다른 음성을 생성 중입니다. 완료 후 다시 시도해 주세요.')
            jid = uuid.uuid4().hex
            jobs[jid] = {'key': key, 'status': 'queued'}
        def work():
            try:
                with lock:
                    jobs[jid]['status'] = 'generating'
                result = generate(package, root / key, config)
                relative = Path(result['audio_path']).relative_to(root).as_posix()
                with lock:
                    jobs[jid].update(status='complete', audio_url='/api/voice-studio/audio/' + relative,
                                     duration_seconds=result['duration_seconds'])
            except Exception as exc:
                with lock:
                    jobs[jid].update(status='failed', error=str(exc))
        executor.submit(work)
        return {'id': jid, **jobs[jid]}

    @router.get('/voices')
    def voices():
        return {'voices': catalog(), 'sample_text': SAMPLE_TEXT}

    @router.get('/choice/{key}')
    def choice(key: str):
        return {'choice': read_choice(key)}

    @router.put('/choice/{key}')
    async def put_choice(key: str, request: Request):
        mutation(request)
        try:
            return {'choice': save_choice(key, await request.json())}
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(400, str(exc))

    @router.post('/sample/{voice}')
    def sample(voice: str, request: Request):
        mutation(request)
        try:
            choice = validate_choice({'voice': voice, 'direction': '따뜻하고 차분한 한국어 이야기 낭독.', 'dialogue_mode': 'narrator'})
        except (ValueError, TypeError):
            raise HTTPException(400, '지원하지 않는 목소리입니다.')
        config = config_with_choice(load_config(), choice)
        package = {'voice_segments': [{'id': 'sample', 'preset': config['narrator_preset'], 'text': SAMPLE_TEXT}]}
        return enqueue('sample-' + voice, package, config)

    @router.post('/generate')
    async def render(request: Request):
        mutation(request)
        body = await request.json()
        text = body.get('script')
        if not isinstance(text, str) or not text.strip() or len(text) > 30000:
            raise HTTPException(400, '대본은 1~30,000자로 입력해 주세요.')
        try:
            choice = validate_choice(body.get('choice'))
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))
        config = config_with_choice(load_config(), choice)
        # The script + choice identify immutable audio; a later edit cannot replace it.
        key = 'script-' + hashlib.sha256(json.dumps([text, choice], sort_keys=True).encode()).hexdigest()
        return enqueue(key, {'script': text}, config)

    @router.get('/jobs/{jid}')
    def status(jid: str):
        with lock:
            if jid not in jobs:
                raise HTTPException(404, '작업을 찾을 수 없습니다. 워커 재시작 후에는 생성을 다시 눌러 저장된 음성을 불러오세요.')
            return {'id': jid, **jobs[jid]}

    @router.get('/audio/{relative:path}')
    def audio(relative: str):
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or path.suffix != '.wav' or not path.is_file():
            raise HTTPException(404, '음성 파일을 찾을 수 없습니다.')
        return FileResponse(path, media_type='audio/wav')

    return router
