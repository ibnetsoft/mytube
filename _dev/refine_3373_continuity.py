import sys,json,subprocess,shutil,hashlib
from pathlib import Path
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'output/codex-local-console/image-repair-3373'
n=53;parent=out/'generated'/f'scene-{n:03}';work=parent/'continuity-v2';work.mkdir(exist_ok=True)
target=work/'edit-target.png';reference=work/'preceding-scene52.png'
shutil.copy2(parent/'normalized.png',target);shutil.copy2(out/'scene-052.png',reference)
response=work/'receipt.json';output=work/'edited.png'
correction="Change ONLY Daigoro's outfit to the same ragged charcoal-grey kimono worn in the preceding scene52 reference: coarse patched fabric, frayed and torn sleeves and hems, grey inner collar. Remove his clean blue-grey haori and grey formal hakama. His old white-haired face, hair knot, exact collapsed pose and position must stay unchanged. Preserve all other people, rice bales, storefronts, framing, lighting, colors, linework and complete background. No blood or injury depiction. This is an outfit continuity correction only."
task=f'Use imagegen skill and BUILT-IN image_gen tool to EDIT one image. First inspect {target} and {reference} with view_image; pass BOTH paths in referenced_image_paths. Image1 is edit target, image2 is preceding scene clothing reference. {correction} One opaque16:9PNG. No externalAPI, Gemini, code-drawn art or delegation. On refusal/unavailable stop; no retry/rephrasing. Copy actual generated PNG unchanged to {output}; inspect it; return JSON only {{"status":"ready","generator":"builtin_image_gen"}}.'
cmd=['codex','exec','--ephemeral','--skip-git-repo-check','--sandbox','workspace-write','--color','never','--json','-C',str(work),'--output-last-message',str(response),'--','-']
with (work/'events.jsonl').open('w',encoding='utf8') as stdout,(work/'stderr.log').open('w',encoding='utf8') as stderr:
 done=subprocess.run(cmd,input=task,text=True,encoding='utf8',stdout=stdout,stderr=stderr,timeout=1800)
assert done.returncode==0 and response.exists() and output.exists()
r=json.loads(response.read_text(encoding='utf8').strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip());assert r['status']=='ready' and r['generator']=='builtin_image_gen'
shutil.copy2(parent/'normalized.png',parent/'normalized-v1.png');shutil.copy2(parent/'generation.json',parent/'generation-v1.json')
im=Image.open(output);ImageOps.fit(im.convert('RGB'),(1920,1080),method=Image.Resampling.LANCZOS).save(parent/'normalized.png')
receipt=json.loads((parent/'generation.json').read_text(encoding='utf8'));receipt.update({'sha256':hashlib.sha256((parent/'normalized.png').read_bytes()).hexdigest(),'revision':'continuity-v2','native_edited_source':str(output),'original_size':im.size})
(parent/'generation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
(parent/'prompt.txt').write_text((parent/'prompt.txt').read_text(encoding='utf8')+'\nScene-specific continuity correction, taking priority over usual wardrobe: '+correction,encoding='utf8')
print('REFINED',n,flush=True)
