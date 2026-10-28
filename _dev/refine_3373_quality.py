import sys,json,subprocess,shutil,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'output/codex-local-console/image-repair-3373'
specs={56:('Change ONLY the two brothers hair knots to the SAME small compact upright rounded black topknots and pale ties in reference2 and reference3. Remove the enlarged sideways spiky fan tuft on the left elder brother. Preserve full unshaved black scalp, hairline, faces and the elder brother thin moustache exactly as his original approved scene39 crop. His moustache is part of the source identity, not an error; do not add a full beard. Preserve all people, pose, clothes, background, framing, light, colors and cel style.',['reference-sentaro.png','reference-jiro.png']),61:('Remove ONLY the written calligraphy glyphs in the upper-left background hanging scroll. Keep its painted landscape, paper texture, frame and placement. Preserve exactly all people, hair, faces, clothes, hands, blank papers, objects, framing, lighting and cel style. No other changes.',[])}
specs[98]=('Remove ONLY the sword and scabbard tucked at Daigoro the central white-haired father waist. He is a merchant, not a sword-bearing samurai. Restore the underlying black crested kimono and grey hakama fabric cleanly. Preserve his body, face, hair, hands, pose, all other people and their faces/hair/clothes, background, framing, lighting and original cel style. No other changes.',[])
specs[99]=specs[98]
specs[101]=('Change ONLY the father hair at the center of this rear-view family walking scene. At the VERY TOP of his head, ABOVE the existing white back hair and on BOTH SIDES of his small knot, there is still a TAN/ORANGE semicircular bare-skin patch. That ENTIRE top scalp patch must become WHITE/PALE-GREY HAIR with fine swept-back grey hair strands. There must be ZERO orange or tan skin anywhere on the TOP of the head; skin is visible only on ears and neck. This is full unshaved white hair, NOT a chonmage shaved crown. Match full hair coverage and modest white knot as reference2. Keep the knot small and preserve his head outline, position and perspective. Preserve all other people, hairstyles, bodies, hands, black formal robe and grey hakama, background, framing, lighting and exact cel style. No other changes.',['reference-大五郎.png'])
specs[100]=('Remove ONLY the two small guards standing in the far-left background doorway. Restore the timber doorway, wall and street behind them. The only people in this image must be the three foreground family members: white-haired Daigoro, cream-kimono Osuzu, brown-kimono Otoku. Preserve exactly all three foreground people, faces, hair, clothes, pose, hands, framing, sunset light and cel style. No other changes.',[])
def refine(n):
 correction,refs=specs[n];parent=out/'generated'/f'scene-{n:03}';version='quality-v3' if n==101 and (parent/'generation.json').exists() and json.loads((parent/'generation.json').read_text(encoding='utf8')).get('revision')=='quality-v2' else 'quality-v2';work=parent/version;work.mkdir(exist_ok=True)
 target=work/'edit-target.png';shutil.copy2(parent/'normalized.png' if (parent/'normalized.png').exists() else parent/'scene.png',target);paths=[str(target)]
 for f in refs:shutil.copy2(out/f,work/f);paths.append(str(work/f))
 response=work/'receipt.json';output=work/'edited.png'
 task=f'Use imagegen skill and BUILT-IN image_gen tool to EDIT one image. First inspect each of these paths with view_image, then pass all paths in referenced_image_paths: {json.dumps(paths,ensure_ascii=False)}. Image1 is target. {correction} One opaque16:9PNG. No externalAPI, Gemini, code-drawn art or delegation. On refusal/unavailable stop; no retry/rephrasing. Copy actual generated PNG unchanged to {output}; inspect it; return JSON only {{"status":"ready","generator":"builtin_image_gen"}}.'
 cmd=['codex','exec','--ephemeral','--skip-git-repo-check','--sandbox','workspace-write','--color','never','--json','-C',str(work),'--output-last-message',str(response),'--','-']
 with (work/'events.jsonl').open('w',encoding='utf8') as stdout,(work/'stderr.log').open('w',encoding='utf8') as stderr:
  done=subprocess.run(cmd,input=task,text=True,encoding='utf8',stdout=stdout,stderr=stderr,timeout=1800)
 assert done.returncode==0 and response.exists() and output.exists()
 r=json.loads(response.read_text(encoding='utf8').strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip());assert r['status']=='ready' and r['generator']=='builtin_image_gen'
 if (parent/'generation.json').exists():
  previous='v2' if version=='quality-v3' else 'v1';shutil.copy2(parent/'generation.json',parent/f'generation-{previous}.json');shutil.copy2(parent/'normalized.png',parent/f'normalized-{previous}.png')
 im=Image.open(output);target=parent/'normalized.png';ImageOps.fit(im.convert('RGB'),(1920,1080),method=Image.Resampling.LANCZOS).save(target)
 row=next(x for x in json.loads((out/'audit.json').read_text(encoding='utf8'))['scenes'] if x['number']==n)
 r.update({'number':n,'path':str(target),'original_size':im.size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'revision':version,'native_edited_source':str(output),'visible_characters':row['visible_characters'],'issues':row['issues']})
 (parent/'generation.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
 (parent/'prompt.txt').write_text((parent/'prompt.txt').read_text(encoding='utf8')+'\nScene-specific correction: '+correction,encoding='utf8')
 print('REFINED',n,flush=True)
numbers=list(map(int,sys.argv[sys.argv.index('--only')+1].split(','))) if '--only' in sys.argv else list(specs)
with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(refine,numbers))
