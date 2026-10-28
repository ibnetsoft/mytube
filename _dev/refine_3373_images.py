import sys,json,subprocess,shutil,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'output/codex-local-console/image-repair-3373'
def refine(n):
 parent=out/'generated'/f'scene-{n:03}';work=parent/'wardrobe-v2';work.mkdir(exist_ok=True)
 target=work/'edit-target.png';reference=work/'father-reference.png';shutil.copy2(parent/'normalized.png',target);shutil.copy2(out/'reference-大五郎.png',reference)
 response=work/'receipt.json';output=work/'edited.png'
 task=f'Use imagegen skill and BUILT-IN image_gen tool to EDIT one image. First inspect {target} and {reference} with view_image, then pass BOTH paths in referenced_image_paths. Image1 is edit target, image2 is father identity and BLUE-GREY garment reference. Change ONLY Daigoro\'s clothing: the white-haired72-year-old father must wear a BLUE-GREY haori over INDIGO kimono, grey hakama. NO black formal court robe or formal crests on the father, because this is before the court hearing. Preserve exactly all faces, hairlines, knots, positions, expressions, hands, the two sons\' maroon/dark brown and ochre/dark olive clothing, background, framing, objects, lighting and original cel style. Do not redraw or redesign any other person. One opaque16:9PNG. No externalAPI, no Gemini, no code-drawn art, no delegation. On refusal or unavailable stop with status; no retry/rephrasing. Copy actual generated PNG unchanged to {output}; inspect it; return JSON only {{"status":"ready","generator":"builtin_image_gen"}}.'
 cmd=['codex','exec','--ephemeral','--skip-git-repo-check','--sandbox','workspace-write','--color','never','--json','-C',str(work),'--output-last-message',str(response),'--','-']
 with (work/'events.jsonl').open('w',encoding='utf8') as stdout,(work/'stderr.log').open('w',encoding='utf8') as stderr:
  done=subprocess.run(cmd,input=task,text=True,encoding='utf8',stdout=stdout,stderr=stderr,timeout=1800)
 assert done.returncode==0 and response.exists() and output.exists()
 r=json.loads(response.read_text(encoding='utf8').strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip());assert r['status']=='ready' and r['generator']=='builtin_image_gen'
 shutil.copy2(parent/'normalized.png',parent/'normalized-v1.png');shutil.copy2(parent/'generation.json',parent/'generation-v1.json')
 im=Image.open(output);ImageOps.fit(im.convert('RGB'),(1920,1080),method=Image.Resampling.LANCZOS).save(parent/'normalized.png')
 receipt=json.loads((parent/'generation.json').read_text(encoding='utf8'));receipt.update({'sha256':hashlib.sha256((parent/'normalized.png').read_bytes()).hexdigest(),'revision':'wardrobe-v2','native_edited_source':str(output),'original_size':im.size})
 (parent/'generation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
 prompt=(parent/'prompt.txt').read_text(encoding='utf8');prompt+='\nScene-specific wardrobe correction: Daigoro wears BLUE-GREY haori over INDIGO kimono and grey hakama in THIS pre-hearing shot. No formal black court robe or formal crests on Daigoro. Retain all other scene people and their fixed original references.'
 (parent/'prompt.txt').write_text(prompt,encoding='utf8');print('REFINED',n,flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(refine,[30,41,44]))
