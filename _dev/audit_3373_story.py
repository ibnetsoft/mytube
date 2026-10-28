import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.codex_content_runner import CodexStagedContentRunner
out=ROOT/'output/codex-local-console/image-repair-3373'
manifest=json.loads((out/'manifest.json').read_text(encoding='utf8'))
original=json.loads((ROOT/'_dev/artifacts/image_repair_3373/topic.before.json').read_text(encoding='utf8'))[0]['pregenerated_structure']
refs=[out/'reference-sentaro.png',out/'reference-jiro.png',out/'reference-大五郎.png',out/'reference-お鈴.png',out/'reference-お徳.png']
contacts=sorted(out.glob('contact-*.jpg'))
context={'scenes':[{'number':s['number'],'text':s['text'],'original_shot':s['image_prompt'].split(f"Scene {s['number']}:")[-1].split('Specific story')[0]} for s in manifest], 'characters':original['characters'], 'fixed_designs':{'仙太郎':'42, broad angular face, full black swept-back hair with NO shaved scalp, compact upright topknot, maroon kimono and dark-brown haori. Match provided crop from scene39.', '次郎':'38, narrow face, full black swept-back hair with NO shaved scalp, compact upright topknot, ochre kimono and dark-olive haori. Match provided crop from scene39.', '大五郎':'72, approved white swept-back full hair and modest knot. In courtroom hearing from scene74 onward must wear black crested kimono/hakama; in genuine flashbacks use stated age and then-period hair, not automatically72/white.'}, '_local_image_paths':[str(p) for p in [*refs,*contacts]]}
task='Audit ALL supplied scene images 19-101, against exact Japanese script and preceding/following context. Contact sheets label every scene. First five images are fixed reference crops/portraits. Two sons have inconsistent shaved vs unshaved head, hair knots and age; lock the full-black hair and topknots of scene39. In scene62 the father was wrongly drawn gripping documents; it must be Sentaro with Jiro, father absent. Existing images also incorrectly show the father as Jiro in scene57, and show wrong people in33/34, and white-haired father in younger flashbacks. Detect ALL wrong identities, hair, clothing, cast, setting, story actions or age. Do not treat a mere quoted or mentioned person as physically present. Preserve the storyline, timing, original style jidaigeki_cel. Return {"scenes":[{"number":19,"visible_characters":["canonical names"],"regenerate":false,"issues":["Korean reason"],"shot_en":"scene-specific corrected English image composition/action/environment only, 70-120 words, no full cast appendix"},...]} covering exactly 19-101. Actual hearing must be courtroom, magistrate black-clad formal and elevated as judge, father black crested formal outfit; distinguish father from magistrate. Valid minimal fragments may use preceding context. Preserve original ages for17-year-oldOsuzu and child/infantflashbacks, no sexualization or romantic framing with her father, no injurygraphic detail. For potentially ambiguous minor hair at this resolution mark issue and regenerate when sons appear inconsistent. Do not generate any images or modify any files. Return JSON only.'
import subprocess
input_path=out/'audit-input.json'; input_path.write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf8')
response=out/'audit-response.json'
cmd=['codex','exec','--ephemeral','--sandbox','read-only','--color','never','-C',str(ROOT),'--output-last-message',str(response),'--disable','apps','--disable','plugins']
for p in [*refs,*contacts]:cmd+=['--image',str(p)]
cmd+=['--','-']
with (out/'audit.stdout.log').open('w',encoding='utf8') as stdout,(out/'audit.stderr.log').open('w',encoding='utf8') as stderr:
 done=subprocess.run(cmd,input=f'Read {input_path}. '+task,text=True,encoding='utf8',stdout=stdout,stderr=stderr,timeout=1800)
assert done.returncode==0 and response.is_file(),'Visual audit did not finish'
raw=response.read_text(encoding='utf8').strip();raw=raw.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
result=json.loads(raw)
assert sorted(s['number'] for s in result['scenes'])==list(range(19,102))
(out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print('AUDIT READY',len([s for s in result['scenes'] if s['regenerate']]),flush=True)
