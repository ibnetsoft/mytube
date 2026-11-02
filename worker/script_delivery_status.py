"""Reconcile supervised delivery against its real exclusive process lock."""
import errno
import json
import re
import threading
import time
from pathlib import Path


def active(root, identity):
    if not re.fullmatch(r'[a-f0-9]{32}', str(identity)):
        return None
    directory = Path(root) / identity / 'delivery'
    try:
        data = json.loads((directory / 'status.json').read_text('utf-8-sig'))
        if data.get('source_job_id') != identity or data.get('status') in ('completed', 'canceled'):
            return None
        with (directory / 'supervisor.lock').open('r+b') as stream:
            if __import__('os').name == 'nt':
                import msvcrt
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    return data if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) else None
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return data
                fcntl.flock(stream, fcntl.LOCK_UN)
    except (OSError, ValueError):
        return None
    return None


def reconcile(store, root, identity):
    execution = active(root, identity)
    rows, _ = store.request('GET', 'script_worker_jobs', params={
        'id': 'eq.' + identity, 'select': 'id,status,updated_at,job_record'})
    if not rows:
        return
    row = rows[0]
    job = dict(row['job_record'])
    if row['status'] in ('completed', 'canceled', 'approved_pending_repair'):
        return
    if execution:
        # Preserve the producer's state separately from this live UI overlay.
        # A delivery worker waiting on the row must not wait on itself forever.
        if not job.get('delivery_active') or row['status'] != 'running':
            job['delivery_source_status'] = row['status']
        raw = execution.get('stage') or '저장 단계 복구'
        batch = re.search(r'batch_(\d+)_(\d+)', raw)
        stage = ('복구 대기 · 자동 재시도' if execution.get('status') == 'retry_wait' else
                 f'복구 중 · 씬 연출 {int(batch[1])}~{int(batch[2])}' if batch else '복구 중 · ' + raw)
        state = 'running'
        if job.get('error'):
            job['previous_error'] = job['error']
        job.update(error='', delivery_active=True, delivery_stage=raw)
    elif job.get('delivery_active') and row['status'] == 'running':
        state, stage = 'interrupted', '복구 프로세스 종료 · 재개 필요'
        job['delivery_active'] = False
    else:
        return
    if job.get('status') == state and job.get('stage') == stage and job == row['job_record']:
        return
    stamp = time.time()
    job.update(status=state, stage=stage, updated_at=stamp)
    # Never overwrite candidates/results, or a concurrent publisher/cancel action.
    store.request('PATCH', 'script_worker_jobs', params={
        'id': 'eq.' + identity, 'status': 'eq.' + row['status'],
        'job_record->>stage': 'eq.' + str(row['job_record'].get('stage') or '')},
        body={'status': state, 'updated_at': stamp, 'job_record': job})


def start(store, root):
    stop = threading.Event()
    def run():
        while not stop.is_set():
            for path in Path(root).glob('*/delivery/status.json'):
                try:
                    reconcile(store, root, path.parent.parent.name)
                except Exception:
                    # Database interruptions never stop the actual delivery worker.
                    pass
            stop.wait(5)
    threading.Thread(target=run, name='delivery-status', daemon=True).start()
    return stop
