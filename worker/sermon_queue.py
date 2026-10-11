"""Long-form media runs in the active local web worker, never the retired manager."""
import json
import threading
from pathlib import Path
from worker.sermon_chapters import fingerprint, save


def enqueue(jobs, identity, voice_id=''):
    with jobs.lock:
        return _enqueue(jobs, identity, voice_id)


def _enqueue(jobs, identity, voice_id):
    bundle = jobs.load(identity)
    row, candidate = bundle['job'], bundle['candidate']
    if row.get('approved_hash') != fingerprint(candidate) or not candidate.get('sermon_plan'):
        raise ValueError('현재 설교 대본의 승인 기록이 필요합니다.')
    request = bundle['request']
    previous = row.get('sermon_media', {})
    if voice_id and voice_id != request.get('sermon_voice_id'):
        if previous.get('status'):
            raise ValueError('제작을 시작한 설교의 음성 설정은 변경할 수 없습니다.')
        request['sermon_voice_id'] = voice_id
        save(jobs.root / identity / 'request.json', request)
    if not request.get('sermon_voice_id'):
        raise ValueError('설교 생성 시 ElevenLabs 음성 ID를 지정하세요.')
    if previous.get('status') in ('audio', 'video', 'assembling', 'queued'):
        return previous
    result = {**previous, 'status': 'queued', 'error': ''}
    jobs.update(identity, sermon_media=result, stage='통합워커 설교 제작 대기 · 완료 파일 재사용')
    return result


def process(jobs, identity, stop):
    import fcntl
    directory = jobs.root / identity / 'sermon-media'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        _process(jobs, identity, stop)


def _process(jobs, identity, stop):
    from worker.sermon_media_worker import process_sermon, font_path
    bundle = jobs.load(identity)
    request, candidate = bundle['request'], bundle['candidate']
    if bundle['job'].get('approved_hash') != fingerprint(candidate):
        raise ValueError('승인한 설교 대본이 변경되었습니다.')
    config = {'voice_id': request['sermon_voice_id'], 'voice_speed': request.get('sermon_voice_speed', 1.),
              'language': candidate['language'], 'font_path': font_path(candidate['language'])}
    def notify(progress):
        stage = '통합워커 설교 · ' + progress['status']
        if progress.get('current_chapter'):
            stage += f" · {progress['current_chapter']}장"
        jobs.update(identity, sermon_media=progress, stage=stage)
    result = process_sermon(candidate, jobs.root / identity / 'sermon-media', config, notify, stop.is_set)
    jobs.update(identity, sermon_media={k: result[k] for k in ('status', 'completed_chapters', 'duration_seconds', 'timeline', 'error') if k in result},
                stage='설교 최종 영상 저장 · 출력 검토 대기' if result['status'] == 'review_pending' else '설교 제작 중단 · 이어서 작업 가능')


def start_media_loop(jobs):
    stop = threading.Event()
    # Serialized media queue, separate from the script CLI executor. Only explicitly queued/approved
    # jobs run. A process crash preserves the status and resumes on the next worker startup.
    def poll():
        while not stop.is_set():
            identities = list(jobs.rows)
            for identity in identities:
                if stop.is_set():
                    break
                row = jobs.rows.get(identity, {})
                if row.get('sermon_media', {}).get('status') not in ('queued', 'audio', 'video', 'assembling'):
                    continue
                try:
                    process(jobs, identity, stop)
                except Exception as exc:
                    path = Path(jobs.root) / identity / 'sermon-media/media.json'
                    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
                    error = state.get('error') or (str(exc) if isinstance(exc, ValueError) else '설교 제작 설정·연결 확인 필요')
                    jobs.update(identity, sermon_media={'status': 'failed', 'error': error,
                        'completed_chapters': state.get('completed_chapters', 0)}, stage='설교 제작 중단 · 완료 파일 보존')
            stop.wait(3)
    threading.Thread(target=poll, name='sermon-integrated-worker', daemon=True).start()
    return stop
