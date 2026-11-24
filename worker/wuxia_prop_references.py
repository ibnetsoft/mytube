"""Build real image_gen attachment arguments for explicit, present series props.

Example: python -m worker.wuxia_prop_references --prop SEJ_DAGGER_01 --prompt '...'
Pass returned prompt/referenced_image_paths directly to the built-in image_gen tool.
"""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def imagegen_arguments(prompt,prop_ids,reference_paths=()):
    manifest=json.loads((ROOT/'docs/wuxia-props/reference-manifest.json').read_text())
    paths=[str(Path(p).resolve()) for p in reference_paths]
    covered=set();receipts=[]
    for row in manifest['weapon_sheets']:
        selected=set(prop_ids)&set(row['prop_ids'])
        if not selected:continue
        path=ROOT/row['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Fixed prop sheet checksum mismatch')
        paths.append(str(path.resolve()));covered.update(selected)
        receipts.append({'prop_ids':sorted(selected),'reference_path':str(path.resolve()),'sha256':row['sha256']})
    if set(prop_ids)-covered:raise ValueError('Unknown fixed weapon prop ID; do not silently omit its image')
    directive='\nFIXED PROP REFERENCES: '+json.dumps(receipts,ensure_ascii=False)+'\nUse the attached actual weapon sheets as authoritative silhouettes/materials/fittings, not design inspiration. Preserve blade, handle, guard, pommel and matching sheath; do not redesign. Only selected props are present. Character identity and episode custody remain governed by their separate references.'
    return dict(prompt=prompt+directive,referenced_image_paths=list(dict.fromkeys(paths)))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prop',action='append',required=True);p.add_argument('--prompt',required=True);p.add_argument('--reference',action='append',default=[]);a=p.parse_args()
    print(json.dumps(imagegen_arguments(a.prompt,a.prop,a.reference),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
