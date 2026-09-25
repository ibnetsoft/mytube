"""User-approved age-reference rebuild; retain prior attempts and all unaffected assets."""
import copy, hashlib, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
from draft_3292_scoped import OUT, PID, UID
from check_3292_current import capture
from worker import image_recovery as recovery

DEST=OUT/'scene-assets/flashback-v2'
MANIFEST=DEST/'manifest.json'
STATE=DEST/'manifest.recovery.json'

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def event(e):return recovery.update_file(STATE,lambda s:recovery.transition(s,e))

def prepare():
    assert not MANIFEST.exists()
    before=capture()
    assert len(before['linked_projects'])==1
    scenes=before['topic'][0]['pregenerated_structure']['scenes']
    assert len(scenes)==53 and [s['scene_number'] for s in scenes if not s.get('image_url')]==[21,22,23,24]
    DEST.mkdir(parents=True,exist_ok=True)
    write(DEST/'before-generation.json',before)
    chars=[
      {'id':'geumrye38','kind':'character','layout':'single','scene_numbers':[],'references':[],
       'prompt':'Use case: historical-scene. Photorealistic character reference portrait, single waist-up person, square canvas. Fictional Korean woman Geumrye, age38, late Joseon village. Clearly a woman in her late thirties, not an elderly woman: firm youthful cheeks, smooth forehead with only very faint expression lines, full black hair without gray in a simple low bun with plain wooden pin. Broad rounded-square face, broad cheekbones, gently hooded dark brown eyes, straight short nose, small dark mole on HER LEFT cheek (viewer right), medium-width lips. Natural unretouched skin with pores, no glamorous makeup. She wears a fully closed ochre-brown cotton jeogori with ivory collar and dark tie, indigo chima. Neutral gently serious expression, relaxed hands, ordinary upright posture. Soft daylight against plain earth-plaster wall. Late-thirties appearance is essential; do not add deep wrinkles, sagging cheeks, age spots or gray hair. No other people, writing, labels, collage, jewelry or modern props.'},
      {'id':'sunduk12','kind':'character','layout':'single','scene_numbers':[],'references':[],
       'prompt':'Use case: historical-scene. Photorealistic age-appropriate character reference, one fictional Korean CHILD named Sunduk, twelve years old, late Joseon village. Single waist-up portrait on square canvas. Clearly a preteen child with a small narrow-oval face, soft rounded juvenile cheeks, short childlike jaw, dark brown gently downturned eyes, small nose and mouth, naturally smooth skin; child-sized slim shoulders and proportions. Black center-parted hair tied into one simple braid, no adult bun. Fully clothed in loose modest muted dusty-blue cotton hanbok jeogori with ivory collar and charcoal chima, no makeup or jewelry. Calm thoughtful neutral expression. Soft natural daylight, plain earth-plaster wall. Ordinary historical family-story portrait, no danger or violence. Do not depict an adult, teenager-looking fashion model, wrinkles, makeup, adult facial proportions, text, labels, collage or modern props.'}
    ]
    old=read(OUT/'scene-assets/recovery-21-24/approved-alternatives.json')
    shared='Use case: historical-scene. One single widescreen16:9 photorealistic still, no collage. Late Joseon rural Korea. Reference1 is the exact approved character Geumrye age38: retain her late-thirties face, black hair, mole on left cheek, ochre-brown jeogori and indigo skirt. Do not age her up. Natural light and worn cotton textures, period-accurate surroundings. No modern items, captions, legible writing or watermark. '
    jobs=chars[:]
    for n,p in zip(range(21,25),old['proposals']):
        scene_action=p['prompt'].split(f'Scene{n}:',1)[1]
        if n==24:
            scene_action=scene_action.split('Reference image2')[0]+'Reference2 is the exact approved child Sunduk age12: preserve her CHILD face, small child proportions, black braid and muted-blue hanbok. Do not turn her into an adult. Both fully clothed, seated apart. Quiet family disagreement, no threats, injuries or physical violence. Eye-level medium-wide framing.'
        jobs.append({'id':f'scene{n}','kind':'scene','layout':'single','scene_numbers':[n],
          'references':[str(DEST/'geumrye38.png')]+([str(DEST/'sunduk12.png')] if n==24 else []),
          'prompt':shared+f'Scene{n}:'+scene_action})
    manifest={'schema':'cowork_scene_assets/v1','topic_id':3292,'scene_count':4,
      'recovery_policy':recovery.POLICY,'jobs':jobs,
      'grids':[{'grid_number':6,'scene_numbers':[21,22,23,24],'prompt':'Individual approved scene jobs; no grid generation','raw_file':'unused.png'}],
      'scene_specs':[s for s in scenes if s['scene_number'] in [21,22,23,24]],
      'authorization':{'user_message':'이어가','scope':'New age-specific references then regenerate four approved benign scenes after prior visual-age QA failure.',
          'previous_history':str(OUT/'scene-assets/recovery-21-24/manifest.recovery.json'),'previous_status':'quality_failed; history not reset or overwritten'}}
    write(MANIFEST,manifest)
    # Compile explicitly authorized individual jobs, not the legacy grid initializer.
    state=recovery.initialize({'jobs':jobs});state['source_hash']=recovery.digest(manifest)
    state['authorization']=manifest['authorization'];write(STATE,state)
    print('New user-approved reference-first revision prepared;53-scene source intact.')

def start(job_id):
    if job_id.startswith('scene'):
        state=read(STATE)
        for key in ('geumrye38','sunduk12'):
            job=recovery.get_job(state,key);assert job['status']=='ready';recovery.verify_file(job)
    state=event({'action':'start','job_id':job_id})
    job=recovery.get_job(state,job_id)
    print(json.dumps({k:job[k] for k in ('id','prompt','references')},ensure_ascii=False))

def accept(job_id,source,review):
    dest=DEST/(job_id+'.png');source=Path(source)
    if dest.exists():assert dest.read_bytes()==source.read_bytes()
    else:shutil.copy2(source,dest)
    event({'action':'result','job_id':job_id,'outcome':'generated','image_file':str(dest)})
    event({'action':'accept','job_id':job_id,'visual_review':review})
    print(job_id+' ready')

if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='start':start(sys.argv[2])
    elif sys.argv[1]=='accept':accept(*sys.argv[2:])
