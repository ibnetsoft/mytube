"""Prepare speaker geometry once before submission; do not generate new voices or mouth patches."""
import copy
import dataclasses
import argparse
import sys
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worker"))

from ae_media_utils import ref as image_reference


class LeaseLost(RuntimeError):
    pass


def process_one(should_stop=None):
    should_stop = should_stop or (lambda: False)
    import ae_highlight_worker as ae
    from ae_mouth import locate_speakers, digest
    from codex_content_runner import CodexStagedContentRunner
    base, headers = ae._supabase()
    url = base + '/rest/v1/std_project_assets'
    jobs = ae._request('GET', url, headers, params={'select':'*','metadata->>kind':'eq.ae_speaker_coordinates','or':f"(metadata->>state.eq.queued,and(metadata->>state.eq.processing,updated_at.lt.{(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()}))",'order':'created_at.asc','limit':'1'}).json()
    if not jobs: return False
    job = jobs[0]; meta = copy.deepcopy(job['metadata'])
    lease = str(uuid.uuid4())
    claimed = ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},params={'id':'eq.'+job['id'],'updated_at':'eq.'+job['updated_at']},json={'metadata':{**meta,'state':'processing','worker_token':lease,'error':None,'heartbeat_at':ae._now()},'updated_at':ae._now()}).json()
    if not claimed: return False
    meta = claimed[0]['metadata']
    guard = threading.Lock()
    stopped = threading.Event()
    lost = threading.Event()
    def save(**changes):
        with guard:
            if lost.is_set(): raise LeaseLost('Coordinate worker lease was lost')
            updated = {**meta, **changes, 'heartbeat_at':ae._now()}
            rows = ae._request('PATCH',url,{**headers,'Prefer':'return=representation'},
                params={'id':'eq.'+job['id'],'metadata->>worker_token':'eq.'+lease},
                json={'metadata':updated,'updated_at':ae._now()}).json()
            if not rows:
                lost.set()
                raise LeaseLost('Coordinate worker lease was lost')
            meta.update(updated)
    def heartbeat():
        while not stopped.wait(15):
            try: save()
            except Exception:
                lost.set()
                return
    ticker = threading.Thread(target=heartbeat, daemon=True)
    ticker.start()
    try:
        runner = CodexStagedContentRunner()
        runner.config = dataclasses.replace(runner.config, timeout_seconds=min(runner.config.timeout_seconds, 180))
        directory = Path(ae.ROOT if hasattr(ae,'ROOT') else Path(__file__).resolve().parents[1]) / 'output' / 'codex-local-console' / 'speaker-coordinates' / meta['fingerprint']
        directory.mkdir(parents=True,exist_ok=True)
        results = {r['number']:r for r in meta.get('results',[])}
        previous = ae._request('GET',url,headers,params={'select':'metadata','project_id':'eq.'+job['project_id'],
            'metadata->>kind':'eq.ae_speaker_coordinates','metadata->>state':'eq.ready','order':'created_at.desc','limit':'100'}).json()
        reusable = [r for old in previous if old['metadata'].get('input',{}).get('cast_key')==meta['input']['cast_key'] for r in old['metadata'].get('results',[])]
        failures = {r['number']:r for r in meta.get('failures',[])}
        for scene in sorted(meta['input']['scenes'],key=lambda s:s['number']):
            if scene['number'] in results: continue
            if should_stop():
                save(state='queued', current_scene=None)
                return True
            save(current_scene=scene['number'])
            try:
                bucket,path = image_reference(scene['image'])
                image = directory / f"scene-{scene['number']}.png"
                if not image.exists(): ae._download_gcs_file(ae.GcsRef(bucket,path),image)
                names = {r['speaker'] for r in scene['rows']}
                cached = next((r for r in reusable if r['image_id']==scene['image']['id'] and r['source_path']==path
                    and r['source_sha256']==digest(image) and names.issubset({v['speaker'] for v in r['speakers']})),None)
                speakers = [r for r in cached['speakers'] if r['speaker'] in names] if cached else locate_speakers(runner,meta['fingerprint']+'-'+str(scene['number'])+'-'+lease,scene,image,scene['rows'],meta['input']['cast'])
                if any(r['status']=='visible' and not r.get('face_box') for r in speakers): raise ValueError('Face bounds are missing')
                results[scene['number']] = {'number':scene['number'],'image_id':scene['image']['id'],'source_path':path,'source_sha256':digest(image),'speakers':speakers}
                failures.pop(scene['number'], None)
                save(results=list(results.values()),failures=list(failures.values()))
            except LeaseLost:
                raise
            except Exception as exc:
                failures[scene['number']] = {'number':scene['number'],'error':str(exc)[:500]}
                save(failures=list(failures.values()))
                continue
        save(state='needs_review' if failures else 'ready', current_scene=None, results=list(results.values()),
             failures=list(failures.values()), error='; '.join(f"Scene {n}: {v['error']}" for n,v in failures.items())[:500] or None,
             reviewer='local-codex-visual-analysis')
    except LeaseLost:
        raise
    except Exception as exc: save(state='needs_review',error=str(exc)[:500])
    finally:
        stopped.set()
        ticker.join(timeout=65)
    return True


def main():
    parser = argparse.ArgumentParser(description='Analyze dialogue characters without After Effects')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    while True:
        try:
            process_one()
        except Exception as exc:
            print('Coordinate worker:', type(exc).__name__, flush=True)
            if args.once: raise
        if args.once: break
        time.sleep(20)


if __name__ == '__main__':
    main()
