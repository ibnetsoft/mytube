"""Restore the checked-in episode snapshot; optionally fetch verified remote assets/readback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def save_new_or_same(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f'Existing work differs; preserve and inspect before restoring: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.restore-tmp')
    temporary.write_bytes(data)
    temporary.replace(path)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', choices=['1', '2', 'all'], default='all')
    parser.add_argument('--assets', action='store_true')
    parser.add_argument('--readback', action='store_true')
    args = parser.parse_args()
    episodes = ['episode-01', 'episode-02'] if args.episode == 'all' else [f'episode-{int(args.episode):02d}']
    source = ROOT / 'docs/wuxia-handoff'
    store = credentials = None
    if args.assets or args.readback:
        from worker.script_worker_store import ScriptStore
        store = ScriptStore()
    if args.assets:
        from worker.cowork_scene_assets import _gcs_credentials
        names = {'sys_api_gcs_bucket_name':'GCS_BUCKET_NAME', 'sys_api_gcs_project_id':'GCS_PROJECT_ID',
                 'sys_api_gcs_client_email':'GCS_CLIENT_EMAIL', 'sys_api_gcs_private_key':'GCS_PRIVATE_KEY'}
        rows, _ = store.request('GET', 'global_settings', params={'select':'key,value', 'key':'in.(' + ','.join(names) + ')'})
        for row in rows:
            if row.get('value'):
                os.environ[names[row['key']]] = str(row['value'])
        credentials, _ = _gcs_credentials()
    manifest = json.loads((source/'snapshot-manifest.json').read_text(encoding='utf-8'))
    for episode in episodes:
        target = ROOT/'output/wuxia-series-rebuild'/episode
        for entry in manifest:
            if entry['episode'] != episode:
                continue
            relative = entry['file']
            data = (source/episode/relative).read_bytes()
            if digest(data) != entry['sha256']:
                raise RuntimeError(f'Snapshot checksum mismatch: {episode}/{relative}')
            if relative == 'image-generation-jobs.json':
                jobs = json.loads(data)
                for job in jobs:
                    job['destination'] = str(target/'images'/(job['asset_id']+'.png'))
                    refs = []
                    for ref in job.get('referenced_image_paths', []):
                        normalized = ref.replace('\\', '/')
                        marker = '/mytube/'
                        if marker in normalized:
                            normalized = str(ROOT/normalized.split(marker, 1)[1])
                        refs.append(normalized)
                    job['referenced_image_paths'] = refs
                data = json.dumps(jobs, ensure_ascii=False, indent=2).encode('utf-8')
            save_new_or_same(target/relative, data)
        for font in [ROOT/'static/fonts/NotoSansKR-Bold.ttf', ROOT/'auth-web/public/fonts/DoHyeon-Regular.ttf', ROOT/'auth-web/public/fonts/BlackHanSans-Regular.ttf']:
            if font.is_file():
                save_new_or_same(target/'fonts'/font.name, font.read_bytes())
        if args.assets:
            import requests
            receipts = json.loads((target/'packaging/asset-upload-receipts.json').read_text(encoding='utf-8'))
            for relative, asset in receipts.items():
                path = (target/relative).resolve()
                if not path.is_relative_to(target.resolve()):
                    raise RuntimeError('Invalid asset relative path')
                if path.is_file() and digest(path.read_bytes()) == asset['sha256']:
                    continue
                url = 'https://storage.googleapis.com/storage/v1/b/' + quote(asset['gcs_bucket'], safe='') + '/o/' + quote(asset['gcs_path'], safe='')
                response = requests.get(url, params={'alt':'media'}, headers={'Authorization':f'Bearer {credentials.token}'}, timeout=120)
                response.raise_for_status()
                if digest(response.content) != asset['sha256']:
                    raise RuntimeError(f'Remote asset hash mismatch: {relative}')
                save_new_or_same(path, response.content)
            print(episode, 'verified remote assets:', len(receipts))
        if args.readback:
            receipt = json.loads((target/'packaging/registration-receipt.json').read_text(encoding='utf-8'))
            rows, _ = store.request('GET', 'topics_queue', params={'select':'*', 'id':'eq.'+str(receipt['topic_id']), 'limit':1})
            if len(rows) != 1 or digest(rows[0]['pregenerated_script'].encode()) != receipt['script_sha256']:
                raise RuntimeError('Registered script changed or is unavailable; do not overwrite/re-register')
            save_new_or_same(target/'packaging/registered-topic-readback.json', json.dumps(rows[0], ensure_ascii=False, indent=2).encode('utf-8'))
            print(episode, 'registered script verified:', receipt['topic_id'])
        print(episode, 'snapshot restored; no topic was created or modified')

if __name__ == '__main__':
    main()
