"""Persist a GCS resumable session so upload failures never require a new render."""
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote
import requests

# Keep each request below the local network's large-body interruption threshold.
# GCS requires non-final chunks to be multiples of 256 KiB.
CHUNK_SIZE = 1024 * 1024

def upload_resumable(file, bucket, path, mime, token):
    file = Path(file)
    size = file.stat().st_size
    with file.open('rb') as stream: sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    receipt = file.with_name(file.name + '.gcs-upload.json')
    expected = {'bucket': bucket, 'path': path, 'sha256': sha, 'size': size}
    saved = json.loads(receipt.read_text()) if receipt.exists() else {}
    session = saved.get('session') if all(saved.get(k)==v for k,v in expected.items()) else None
    for attempt in range(3):
        try:
            if not session:
                response = requests.post(f'https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket,safe="")}/o?uploadType=resumable',
                    headers={'Authorization':'Bearer '+token,'X-Upload-Content-Type':mime,'X-Upload-Content-Length':str(size)},
                    json={'name':path,'contentType':mime}, timeout=(10,60))
                response.raise_for_status();session=response.headers['Location']
                receipt.write_text(json.dumps({**expected,'session':session}))
            status = requests.put(session, headers={'Content-Length':'0','Content-Range':f'bytes */{size}'}, data=b'',timeout=(10,60))
            if status.status_code in (200,201): return status.json()
            if status.status_code in (404,410): session=None;continue
            if status.status_code != 308: status.raise_for_status()
            offset = int(status.headers.get('Range','bytes=0--1').split('-')[-1])+1 if status.headers.get('Range') else 0
            with file.open('rb') as stream:
                stream.seek(offset)
                while offset<size:
                    chunk = stream.read(CHUNK_SIZE)
                    end = offset+len(chunk)-1
                    response = requests.put(session, headers={'Content-Type':mime,'Content-Length':str(len(chunk)),
                        'Content-Range':f'bytes {offset}-{end}/{size}'},data=chunk,timeout=(10,120))
                    if response.status_code in (200,201): return response.json()
                    if response.status_code != 308: response.raise_for_status()
                    acknowledged = response.headers.get('Range')
                    if not acknowledged: raise ValueError('GCS upload did not acknowledge bytes')
                    offset=int(acknowledged.split('-')[-1])+1;stream.seek(offset)
        except (requests.RequestException,ValueError):
            if attempt==2: raise RuntimeError('GCS upload failed after bounded retries') from None
            time.sleep(attempt+1)
    raise RuntimeError('GCS resumable upload retries exhausted')
