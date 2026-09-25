"""Versioned, hash-verified scene storage; explicitly retains blocked scenes as missing."""
import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
from draft_3292_scoped import OUT, save
from scripts.repair_existing_topic_scripts import _headers
from cowork_scene_assets import crop_grids

NATIVE = Path('C:/Users/Pc/.codex/generated_images/01a07157-6d55-7753-8bdc-53780dd4ee46')
FILES = {
    7:'01167032-c154-49fe-ace6-2da7ddd9f182',
    8:'4b0182d6-4a6f-4518-9d00-e5d14c371d5f',
    9:'4d626090-5524-44d8-b9b9-d5da968e5015',
    10:'ee9ffda3-27b0-482a-9729-9d9be9e328cf',
    11:'c89dcd8d-c36b-41cb-a3fb-976669b3c6f7',
    12:'fa35d2d6-2a16-4364-9668-20ccc1ee588a',
    13:'2dae6e54-9b8e-4611-be2e-d58f53d1a573',
    14:'cc55fde8-5504-4203-a3fe-cc464fe04756',
}

def main():
    folder=OUT/'scene-assets'
    for n,identifier in FILES.items():
        source=NATIVE/f'exec-{identifier}.png'
        dest=folder/'raw'/f'grid-{n:03d}.png'
        if dest.exists():
            assert dest.read_bytes()==source.read_bytes()
        else:
            shutil.copy2(source,dest)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    manifest['grids']=[g for g in manifest['grids'] if g['grid_number']!=6]
    manifest['missing_scene_numbers']=[21,22,23,24]
    manifest['completion_status']='partial_imagegen_output_rejected'
    save('scene-assets/partial-manifest.json',manifest)
    cropped=folder/'cropped-partial'
    if not cropped.exists():
        crop_grids(folder/'partial-manifest.json',folder/'raw',cropped)
    files=sorted(cropped.glob('scene-*.png'))
    assert len(files)==49
    assert {int(p.stem.split('-')[1]) for p in files}==set(range(1,54))-{21,22,23,24}
    base,headers=_headers()
    def upload(path):
        blob=path.read_bytes();sha=hashlib.sha256(blob).hexdigest()
        key=f'topics/3292/repairs/79e865def1d9692b/images/{path.stem}-{sha[:12]}.png'
        url=f'{base}/storage/v1/object/public/content-assets/{key}'
        check=requests.get(url,timeout=90)
        if check.status_code!=200:
            response=requests.post(f'{base}/storage/v1/object/content-assets/{key}',headers={**headers,'Content-Type':'image/png','x-upsert':'false'},data=blob,timeout=120)
            response.raise_for_status()
            check=requests.get(url,timeout=90)
        check.raise_for_status()
        assert hashlib.sha256(check.content).hexdigest()==sha
        n=int(path.stem.split('-')[1])
        print(f'Image {n}: uploaded and bytes verified',flush=True)
        return {'scene_number':n,'image_url':url,'sha256':sha,'object_path':key,'width':1920,'height':1080}
    with ThreadPoolExecutor(max_workers=4) as pool:
        assets=list(pool.map(upload,files))
    save('uploaded-scene-images.json',{'status':'partial','missing_scene_numbers':[21,22,23,24],'assets':assets})
    print('Verified 49 images; scenes21-24 missing. No project/queue write in this script.',flush=True)

if __name__=='__main__':main()
