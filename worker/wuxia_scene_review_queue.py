"""Review user-uploaded scene candidates using the local Codex script worker."""
import hashlib
import logging
import threading
from pathlib import Path

from worker.script_worker_store import StoreUnavailable
from worker.wuxia_scene_replacement import ReviewRejected, review_local_candidate, review_scene_continuity

log = logging.getLogger(__name__)
REVIEW_ROOT = Path(__file__).resolve().parents[1] / 'output' / 'codex-local-console' / 'scene-image-reviews'


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def process_one(store, runner=None):
    claimed, _ = store.request('POST', 'rpc/claim_std_scene_image_review', body={})
    if not claimed:
        return False
    job = claimed[0]
    job_id, token = job['id'], job['claim_token']
    def touch():
        valid, _ = store.request('POST', 'rpc/touch_std_scene_image_review', body={'p_id': job_id, 'p_claim_token': token})
        if valid is not True:
            raise RuntimeError('검수 작업 소유권이 변경되었습니다.')
    def mark(status, message, review=None):
        store.request('PATCH', 'std_scene_image_reviews', params={'id': 'eq.' + job_id,
            'status': 'eq.running', 'claim_token': 'eq.' + token},
            body={'status': status, 'error': message, **({'review': review} if review is not None else {})}, prefer='return=minimal')
    try:
        projects, _ = store.request('GET', 'std_projects', params={'id': 'eq.' + job['project_id'],
            'select': 'id,user_id,employee_email,status,submitted_at,updated_at', 'limit': 1})
        scenes, _ = store.request('GET', 'std_project_scenes', params={'id': 'eq.' + job['scene_id'],
            'project_id': 'eq.' + job['project_id'], 'select': 'id,scene_number,updated_at,metadata', 'limit': 1})
        if len(projects) != 1 or len(scenes) != 1:
            mark('conflict', '프로젝트 또는 씬을 찾지 못해 기존 이미지를 유지했습니다.')
            return True
        project, scene = projects[0], scenes[0]
        if (project['updated_at'] != job['project_updated_at'] or scene['updated_at'] != job['scene_updated_at']
            or project.get('submitted_at') or project['status'] not in ('claimed', 'in_progress')
            or scene.get('metadata', {}).get('source_image_sha256') != job['source_sha256']):
            mark('conflict', '프로젝트 또는 씬 원본이 변경되어 기존 이미지를 유지했습니다.')
            return True
        from worker.ae_highlight_worker import GcsRef, _download_gcs_file
        directory = REVIEW_ROOT / job_id
        directory.mkdir(parents=True, exist_ok=True)
        original = directory / 'original-source'
        source_bucket = scene.get('metadata', {}).get('gcs_bucket')
        source_path = scene.get('metadata', {}).get('gcs_path')
        if not source_bucket or not source_path:
            mark('conflict', '현재 원본의 저장소 경로를 확인하지 못해 기존 이미지를 유지했습니다.')
            return True
        if not original.exists():
            _download_gcs_file(GcsRef(source_bucket, source_path), original)
        if _hash(original) != job['source_sha256']:
            mark('conflict', '현재 원본 파일의 해시가 달라 기존 이미지를 유지했습니다.')
            return True
        from PIL import Image
        import shutil
        with Image.open(original) as source_image:
            extension = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}.get(source_image.format)
            source_image.verify()
        if not extension:
            mark('conflict', '현재 원본 이미지 형식을 확인할 수 없어 기존 이미지를 유지했습니다.')
            return True
        named_original = directory / ('original-source' + extension)
        if not named_original.exists():
            shutil.copyfile(original, named_original)
        if _hash(named_original) != job['source_sha256']:
            raise RuntimeError('검수 입력 원본의 해시가 일치하지 않습니다.')
        original = named_original
        candidate = directory / 'candidate.png'
        if not candidate.exists():
            _download_gcs_file(GcsRef(job['candidate_bucket'], job['candidate_path']), candidate)
        if _hash(candidate) != job['candidate_sha256']:
            mark('review_failed', '업로드된 이미지의 해시가 일치하지 않아 기존 이미지를 유지했습니다.')
            return True
        if runner is None:
            from worker.codex_content_runner import CodexStagedContentRunner
            runner = CodexStagedContentRunner()
        try:
            touch()
            continuity = review_scene_continuity(original, candidate, scene_id=scene['metadata'].get('scene_id') or scene['metadata']['cut_id'], runner=runner, scene_context={k: scene['metadata'].get(k) for k in ('cut_id', 'title', 'visual_action', 'image_prompt')})
            touch()
            result = review_local_candidate(candidate, scene={'scene_id': scene['metadata'].get('scene_id') or scene['metadata']['cut_id']},
                current_sha=job['source_sha256'], expected_current_sha=job['source_sha256'],
                asset_id=job_id, runner=runner, check=touch)
            result['continuity_review'] = continuity
        except ReviewRejected as exc:
            mark('review_failed', '이미지 검수를 통과하지 못해 기존 이미지를 유지했습니다.', {'quality_control': exc.evidence})
            return True
        touch()
        # The database applies source, scene, asset and version checks in one transaction.
        try:
            result_db, _ = store.request('POST', 'rpc/apply_std_scene_image_review', body={
                'p_id': job_id, 'p_claim_token': token, 'p_review': result})
        except StoreUnavailable:
            # POST can commit despite a lost response; inspect before retrying.
            recorded, _ = store.request('GET', 'std_scene_image_reviews', params={
                'id': 'eq.' + job_id, 'select': 'status,claim_token', 'limit': 1})
            if recorded and recorded[0].get('status') == 'completed':
                return True
            current, _ = store.request('GET', 'std_projects', params={
                'id': 'eq.' + job['project_id'], 'select': 'updated_at,status,submitted_at', 'limit': 1})
            current_scene, _ = store.request('GET', 'std_project_scenes', params={
                'id': 'eq.' + job['scene_id'], 'select': 'updated_at,metadata->>source_image_sha256', 'limit': 1})
            if (len(current) != 1 or len(current_scene) != 1 or current[0]['updated_at'] != job['project_updated_at']
                    or current_scene[0]['updated_at'] != job['scene_updated_at']
                    or current_scene[0].get('source_image_sha256') != job['source_sha256']):
                mark('conflict', '프로젝트 또는 씬 원본이 변경되어 기존 이미지를 유지했습니다.')
                return True
            raise
        if not isinstance(result_db, dict) or result_db.get('success') is not True:
            raise RuntimeError('교체 결과를 확인하지 못했습니다.')
        return True
    except Exception:
        # A timeout can occur after commit. A conditional patch never changes a
        # completed job or a job that another worker has reclaimed.
        log.exception('Scene image review interrupted: %s', job_id)
        try:
            from datetime import datetime, timedelta, timezone
            delay = min(300, 5 * 2 ** min(int(job.get('attempt_count') or 1), 6))
            store.request('PATCH', 'std_scene_image_reviews', params={'id': 'eq.' + job_id,
                'status': 'eq.running', 'claim_token': 'eq.' + token}, body={
                    'status': 'queued', 'next_attempt_at': (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(),
                    'error': '검수 실행이 지연되어 자동 재시도합니다. 기존 이미지는 유지됩니다.'}, prefer='return=minimal')
        except StoreUnavailable:
            pass  # The expired claim will be recovered when the database returns.
        raise


def start_review_loop(jobs):
    stop = threading.Event()
    def run():
        failures = 0
        while not stop.is_set():
            try:
                if jobs.inflight or not jobs.store:
                    stop.wait(5)
                    continue
                processed = jobs.pool.submit(process_one, jobs.store).result()
                failures = 0
                stop.wait(3 if processed else 20)
            except Exception:
                failures = min(failures + 1, 5)
                stop.wait(min(120, 3 * 2 ** failures))
    threading.Thread(target=run, name='scene-image-review', daemon=True).start()
    return stop
