"""Publish an explicitly selected project's existing SFX as the shared library.
No audio is generated or copied; only verified Storage references are published.
Usage: python -m scripts.publish_sfx_catalog --project-id UUID
"""
import argparse
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
from scripts.repair_existing_topic_scripts import _headers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-id', required=True)
    args = parser.parse_args()
    base, headers = _headers()
    response = requests.get(base+'/rest/v1/std_project_assets', headers=headers, params={
        'project_id':'eq.'+args.project_id, 'metadata->>audio_role':'eq.sfx',
        'status':'in.(uploaded,assigned)', 'select':'id,file_name,file_size,mime_type,metadata', 'limit':1000}, timeout=30)
    response.raise_for_status()
    descriptions = re.findall(r"\['([^']+)', '([^']+)'\]", Path('auth-web/lib/stdSfxDescriptions.ts').read_text(encoding='utf-8'))
    def verified(asset):
        meta = asset.get('metadata') or {}
        path = meta.get('storage_path')
        if not path: return None
        bucket = meta.get('storage_bucket','content-assets')
        probe = requests.get(base+'/storage/v1/object/'+bucket+'/'+path, headers={**headers,'Range':'bytes=0-63'}, timeout=30)
        if probe.status_code not in (200,206) or not probe.content: return None
        description = meta.get('description_ko') or next((d for p,d in descriptions if asset['file_name'].lower().startswith(p.lower())), '')
        return {**asset, 'id':'library:'+asset['id'], 'description_ko':description,
                'metadata':{'audio_role':'sfx','storage_bucket':bucket,'storage_path':path,'description_ko':description}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        items = [x for x in pool.map(verified,response.json()) if x]
    if not items: raise RuntimeError('No readable Storage SFX found; catalog left untouched')
    saved = requests.post(base+'/storage/v1/object/content-assets/sfx-library/catalog.json',
        headers={**headers,'Content-Type':'application/json','x-upsert':'true'},
        data=json.dumps({'version':1,'items':items},ensure_ascii=False).encode(), timeout=30)
    saved.raise_for_status()
    check = requests.get(base+'/storage/v1/object/content-assets/sfx-library/catalog.json', headers=headers,timeout=30)
    check.raise_for_status()
    assert len(check.json()['items']) == len(items)
    print('Published and verified shared SFX catalog:',len(items))


if __name__ == '__main__': main()
