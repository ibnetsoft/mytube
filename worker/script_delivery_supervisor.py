"""Restart the delivery supervisor for explicitly confirmed new script jobs."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from worker.script_delivery_status import active


def eligible(job, request, worker_id):
    return (job.get('worker_id') == worker_id
            and job.get('auto_delivery_requested') is True
            and not job.get('published')
            and job.get('status') in ('queued', 'running', 'awaiting_approval', 'failed', 'interrupted')
            and request.get('mode') == 'new'
            and request.get('settings_confirmed') is True
            and request.get('production_mode', 'standard') == 'standard'
            and str(request.get('category_id') or '').isdigit())


class Supervisor:
    def __init__(self, root, project_root, worker_id, popen=subprocess.Popen, clock=time.monotonic):
        self.root, self.project_root = Path(root), Path(project_root)
        self.worker_id, self.popen, self.clock = worker_id, popen, clock
        self.children = {}
        self.retry_at = {}
        self.failures = {}

    def tick(self):
        for file in self.root.glob('*/job.json'):
            identity = file.parent.name
            if not re.fullmatch(r'[a-f0-9]{32}', identity):
                continue
            try:
                job = json.loads(file.read_text(encoding='utf-8-sig'))
                request = json.loads((file.parent / 'request.json').read_text(encoding='utf-8-sig'))
                if not eligible(job, request, self.worker_id):
                    continue
                child = self.children.get(identity)
                if child and child.poll() is None:
                    continue
                if active(self.root, identity):
                    continue
                now = self.clock()
                if child:
                    self.children.pop(identity, None)
                    failures = self.failures.get(identity, 0) + 1
                    self.failures[identity] = failures
                    self.retry_at[identity] = now + min(300, 10 * 2 ** min(failures, 5))
                if now < self.retry_at.get(identity, 0):
                    continue
                directory = file.parent / 'delivery'
                directory.mkdir(parents=True, exist_ok=True)
                log = (directory / 'automatic-supervisor.log').open('ab')
                try:
                    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
                    self.children[identity] = self.popen(
                        [sys.executable, str(self.project_root / 'scripts' / 'continue_script_topic.py'), '--job', identity],
                        cwd=str(self.project_root), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=flags, close_fds=True)
                finally:
                    log.close()
            except (OSError, ValueError, KeyError):
                # A later scan retries unreadable local state without changing the job.
                continue


def start(root, project_root, worker_id):
    stop = threading.Event()
    supervisor = Supervisor(root, project_root, worker_id)
    def run():
        while not stop.is_set():
            supervisor.tick()
            stop.wait(5)
    threading.Thread(target=run, name='script-delivery-supervisor', daemon=True).start()
    return stop
