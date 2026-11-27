"""Complete the explicitly authorized episode-five script registration only."""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT / 'worker/connection.env', override=False)
from worker.script_worker_store import ScriptStore
from worker.script_topic_delivery import web_readiness, write

JOB = '5a0bb74a8d8f4a2d943fa79bc79c7dcc'
BASE = ROOT / 'output/codex-local-console' / JOB
OUT = ROOT / 'output/pawnshop-series/episode-05'
store = ScriptStore()

def main():
    while True:
        file = BASE / 'delivery/status.json'
        status = json.loads(file.read_text()) if file.exists() else {}
        if status.get('status') == 'canceled':
            return
        if status.get('status') != 'completed':
            time.sleep(15)
            continue
        bundle = store.get(JOB)
        if bundle['job'].get('status') == 'canceled':
            return
        if not bundle['job'].get('published'):
            time.sleep(5)
            continue
        rows, _ = store.request('GET', 'topics_queue', params={
            'select': '*', 'progress_payload->>source_script_job_id': 'eq.' + JOB})
        assert len(rows) == 1, 'Expected exactly one registered episode'
        row = rows[0]
        candidate = bundle['candidate']
        assert row['pregenerated_script'] == candidate['script']
        assert row['pregenerated_structure'] == candidate['structure']
        assert row['publish_metadata'] == candidate['publish_metadata']
        assert web_readiness(row, OUT)['ready'] is True
        scenes = row['pregenerated_structure']['scenes']
        assert scenes
        bundle['job'].update(status='completed', stage='5화 대본 생성·유저웹 등록 완료',
                             published_topic_id=row['id'], topic_queue_id=row['id'],
                             registration_completed_at=time.time(), updated_at=time.time(),
                             completion_scope='script_package_and_user_web_registration',
                             remaining=[])
        revision = store.save(bundle)
        verified = store.get(JOB)
        assert verified['job']['status'] == 'completed'
        assert verified['job']['published'] is True
        write(BASE / 'job.json', {**verified['job'], 'storage_revision': revision,
                                  'sync_status': 'synced', 'sync_error': ''})
        write(OUT / 'COMPLETION_RECEIPT.json', {
            'job_id': JOB, 'topic_id': row['id'], 'status': 'completed',
            'title': row['generated_title'], 'script_chars': len(candidate['script']),
            'scene_count': len(scenes), 'registered_and_readback_verified': True,
            'script_sha256': hashlib.sha256(candidate['script'].encode()).hexdigest(),
            'created_at': bundle['job']['created_at'], 'completed_at': time.time(),
            'quality_report': str(BASE / 'delivery/quality-notes.json')})
        print('episode five registration completed', row['id'], flush=True)
        return

if __name__ == '__main__':
    main()
