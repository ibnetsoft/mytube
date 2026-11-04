"""Accept one real built-in generated image and persist its episode checkpoint."""
import argparse,hashlib,json,shutil
from pathlib import Path
from PIL import Image

def accept(root,asset_id,source):
    root=Path(root);source=Path(source)
    jobs=json.loads((root/'image-generation-jobs.json').read_text(encoding='utf-8'))
    job=next((j for j in jobs if j['asset_id']==asset_id),None)
    if job is None:raise ValueError('Unknown episode asset ID')
    with Image.open(source) as im:im.verify()
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    target=root/'images'/(asset_id+'.png');target.parent.mkdir(exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
        raise ValueError('Preserve existing art; a changed image requires an explicit revision')
    if not target.exists():shutil.copy2(source,target)
    directory=root/'asset-generation-receipts';directory.mkdir(exist_ok=True)
    path=directory/(asset_id+'.json')
    receipt={'asset_id':asset_id,'file':'images/'+target.name,'generated_original':str(source.resolve()),'sha256':digest,
             'prompt':job['prompt'],'references':job.get('referenced_image_paths',[]),'status':'generated'}
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--episode-dir',type=Path,required=True);p.add_argument('--asset-id',required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    print(json.dumps(accept(a.episode_dir,a.asset_id,a.source),ensure_ascii=False))
