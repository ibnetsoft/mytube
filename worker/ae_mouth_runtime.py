"""Manager heartbeat and single-instance lifetime for the mouth worker."""
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta


def claimable_filter():
    stale = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    return f"(metadata->>state.in.(queued,direction_approved),and(metadata->>state.eq.processing,updated_at.lt.{stale}))"


@contextmanager
def instance_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Heartbeat:
    def __init__(self, path, instance_id, interval=3):
        self.path, self.interval = path, interval
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.state = dict(pid=os.getpid(), worker_instance_id=instance_id,
                          status='starting', current_job=None, progress=0,
                          last_error=None, last_success_at=None)

    def update(self, **changes):
        with self.lock:
            self.state.update(changes)
            self.state['heartbeat_at'] = time.time()
            self.state['current_job_id'] = (self.state.get('current_job') or {}).get('id')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.path)

    def __enter__(self):
        self.update()
        def pulse():
            while not self.stop.wait(self.interval):
                self.update()
        self.thread = threading.Thread(target=pulse, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join()
        self.update(status='stopped', current_job=None)
