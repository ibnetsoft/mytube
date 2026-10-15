"""Bounded, resumable GCS downloads shared across submitted renders."""
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import quote
import requests

_locks = {}
_guard = threading.Lock()

def download_cached(source, destination, credentials, root, expected_sha=None):
    bucket, path = source.get('gcs_bucket'), source.get('gcs_path')
    urls = [(source.get('gcs_signed_url'), {})] if source.get('gcs_signed_url') else []
    if bucket and path and credentials:
        urls.append((f'https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe="")}/o/{quote(path, safe="")}?alt=media',
                     {'Authorization': 'Bearer ' + credentials.token}))
    if not urls: raise ValueError('No GCS source')
    last = None
    for url, headers in urls:
        try:
            with requests.head(url, headers=headers, timeout=(10, 30)) as head:
                head.raise_for_status()
                generation = head.headers.get('x-goog-generation') or head.headers.get('ETag')
                size = int(head.headers.get('Content-Length') or 0)
            if not generation and not expected_sha: raise ValueError('Object version unavailable')
            key = hashlib.sha256(json.dumps([bucket, path, expected_sha or generation]).encode()).hexdigest()
            directory = Path(root) / key
            with _guard: lock = _locks.setdefault(key, threading.Lock())
            with lock:
                directory.mkdir(parents=True, exist_ok=True)
                ready, partial = directory / 'data', directory / 'data.part'
                def sha(p):
                    with p.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
                if ready.exists():
                    receipt = json.loads((directory / 'receipt.json').read_text())
                    if sha(ready) != receipt['sha256'] or (expected_sha and receipt['sha256'] != expected_sha):
                        ready.unlink()
                for attempt in range(3):
                    if ready.exists(): break
                    offset = partial.stat().st_size if partial.exists() else 0
                    request_headers = {**headers, 'Range': f'bytes={offset}-', 'If-Match': head.headers.get('ETag', '*')}
                    try:
                        with requests.get(url, headers=request_headers, stream=True, timeout=(10, 120)) as response:
                            if response.status_code == 416 and size and offset == size: pass
                            else:
                                response.raise_for_status()
                                if response.status_code != 206: offset = 0
                                with partial.open('ab' if offset else 'wb') as stream:
                                    for chunk in response.iter_content(1024 * 1024):
                                        if chunk: stream.write(chunk)
                        if size and partial.stat().st_size != size: raise ValueError('Incomplete asset download')
                        actual = sha(partial)
                        if expected_sha and actual != expected_sha:
                            partial.unlink(); raise ValueError('Asset bytes differ from submitted hash')
                        (directory / 'receipt.json').write_text(json.dumps({'sha256': actual, 'generation': generation}))
                        partial.replace(ready)
                    except (requests.RequestException, ValueError):
                        if attempt == 2: raise
                        time.sleep(attempt + 1)
                target = Path(destination)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists(): target.unlink()
                try: os.link(ready, target)
                except OSError:
                    import shutil
                    shutil.copyfile(ready, target)
                return target
        except Exception as exc:
            last = exc
    raise RuntimeError('GCS download exhausted bounded retries') from last
