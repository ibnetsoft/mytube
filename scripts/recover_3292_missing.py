"""Scoped, durable recovery of the four missing approved 3292 illustrations."""
import json
import sys
from pathlib import Path
from draft_3292_scoped import OUT, PID, UID
from check_3292_current import capture
from worker import image_recovery as recovery

DEST=OUT/'scene-assets/recovery-21-24'
MANIFEST=DEST/'manifest.json'

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def prepare():
    assert not MANIFEST.exists(), 'Preserve existing recovery state'
    before=capture()
    assert len(before['linked_projects'])==1
    scenes=before['topic'][0]['pregenerated_structure']['scenes']
    assert len(scenes)==53
    assert [s['scene_number'] for s in scenes if not s.get('image_url')]==[21,22,23,24]
    DEST.mkdir(parents=True,exist_ok=True)
    write(DEST/'before-generation.json',before)
    old=json.loads((OUT/'scene-assets/manifest.json').read_text(encoding='utf-8'))
    grid=next(g for g in old['grids'] if g['grid_number']==6)
    common='Use case: historical-scene. One single widescreen 16:9 photorealistic narrative still, not a collage or grid. Late Joseon rural Korea. Natural skin and worn cotton textures, period-accurate clothing, wooden rooms and paper windows; restrained natural light. No modern items, captions, readable writing, logos or watermark. Reference image 1 is fictional Geumrye at age68; this flashback takes place30 years earlier: depict Geumrye age38, preserving her broad rounded-square face, cheek geometry and small mole on her left cheek, with black hair in a low bun and naturally younger skin. Ochre-brown jeogori and indigo skirt. No extra characters. '
    prompts=[
      common+'Scene21: Inside a modest room, Geumrye sits beside a small pile of winter clothing, carefully searching the stitched inner lining of a folded winter jeogori for her hidden pledge paper. Concentrate on her hands opening the lining and her intent, worried face. Medium close view of woman and garment. She is fully dressed. A quiet search, no confrontation or grabbing.',
      common+'Scene22: A close-medium view of Geumrye seated at a low wooden table, pressing her inked thumb onto a traditional field deed on handmade paper. Her face is serious and resigned, not smiling. The document is angled away, its faint marks not legible. Hands and face visible, natural anatomy. This is the solemn loss of her field, not a celebration. No other person is shown.',
      common+'Scene23: Geumrye stands alone on a village dirt lane, holding a small recovered folded pledge paper close to her waist, looking toward the distant closed wooden gate of a wealthy tiled-roof house. Wide composition, subdued overcast daylight, quiet isolation and hesitation. The gate stays distant. No writing on the paper is readable.',
      common.replace('No extra characters.','Only the two specified characters.')+'Scene24: A quiet mother-daughter conversation inside their modest room. Geumrye age38 sits nearby speaking with a sorrowful, restrained expression, hands resting on her lap. Her daughter Sunduk age12 turns her head away and covers her ears with her hands, reluctant to listen. Reference image2 is Sunduk as an adult; preserve her narrow face and family resemblance but render her actual twelve-year-old childhood appearance, black center-parted hair, simple muted-blue cotton hanbok. Fully clothed, ordinary family disagreement; no injury, threats, physical contact or violence. Eye-level medium-wide framing shows both faces and their separate seated positions.'
    ]
    manifest={'schema':'cowork_scene_assets/v1','topic_id':3292,'scene_count':4,
      'recovery_policy':recovery.POLICY,'grids':[grid],
      'scene_specs':[s for s in scenes if s['scene_number'] in [21,22,23,24]],
      'character_references':[str(OUT/'scene-assets/character-reference-3.png'),str(OUT/'scene-assets/character-reference-2.png')]}
    write(MANIFEST,manifest)
    state=recovery.initialize(manifest)
    job=state['jobs'][0]
    job.update(status='safety_review',attempts=2,failure_kind='safety')
    job['history']=[{'action':'historical_import','outcome':'safety','code':'output_safety','request_id':rid,'reason':'Previously observed refusal; detailed reason unavailable. Imported, not a new call.'} for rid in ['1130e816-9583-4955-a3a2-ae60f52ea42e','8dce9a7c-3d42-4ad0-b689-bcfff9d520e7']]
    event={'action':'review','job_id':'grid-006','decision':'alternative','review':{
      'reviewer':'Codex','reason':'Individually reviewed benign garment search, thumbprint, distant gate, and nonviolent family conversation depictions.',
      'source_fidelity':'Keeps pledge in lining, field deed thumbprint, recovered proof and isolation, daughter refusing to listen. No narration change.',
      'character_age_style_preserved':'Geumrye38 and Sunduk12 remain their true flashback ages; preserve DNA and realistic Joseon setting.',
      'safety_assessment':'allowed_alternative','user_approval':'User approved previously proposed alternatives: 아까 생성못한거 이 기준으로 다시 해봐'},
      'proposals':[{'scene_numbers':[n],'prompt':p} for n,p in zip(range(21,25),prompts)]}
    state=recovery.transition(state,event)
    write(recovery.state_path(MANIFEST),state)
    write(DEST/'approved-alternatives.json',event)
    print('Prepared four reviewed single-scene jobs. Existing49 images unchanged.')

def final_review():
    import shutil
    native=Path('C:/Users/Pc/.codex/generated_images/01a07157-6d55-7753-8bdc-53780dd4ee46/exec-0748d0e8-8ad6-4a5c-bd3f-136ace0da61e.png')
    dest=DEST/'scene-024-raw.png'
    if dest.exists():assert dest.read_bytes()==native.read_bytes()
    else:shutil.copy2(native,dest)
    def review(state):
        state=recovery.transition(state,{'action':'result','job_id':'grid-006-alt-4','outcome':'generated','image_file':str(dest)})
        state=recovery.transition(state,{'action':'reject_quality','job_id':'grid-006-alt-4','reason':'Sunduk looks adult rather than12; Geumrye also looks substantially older than38.'})
        for job in state['jobs']:
            if job['status']=='ready':
                # Human final cross-scene QA can revoke an earlier provisional acceptance.
                job['history'].append({'action':'final_quality_revocation','previous_status':'ready',
                    'reviewer':'Codex','reason':'Cross-scene review: adult/elder reference dominated flashback age38. Earlier action/style check was insufficient.',
                    'at':recovery.time.time()})
                job.update(status='quality_failed',failure_kind='quality')
        return state
    state=recovery.update_file(recovery.state_path(MANIFEST),review)
    report={'topic_id':3292,'project_id':PID,'generated_count':4,'safety_refusals_this_run':0,
      'final_quality_accepted':0,'db_writes':0,'storage_uploads':0,
      'status':'quality_review_required_attempt_budget_exhausted',
      'reason':'Flashback ages38/12 not convincingly represented; older reference portraits dominated. No automatic extra generation.',
      'next_proposal':'Create and visually approve dedicated flashback references for Geumrye38 and Sunduk12 before a separately approved new generation pass.',
      'jobs':[{'id':j['id'],'scene_numbers':j['scene_numbers'],'status':j['status'],'attempts':j['attempts'],'image_file':j.get('image_file'),'sha256':j.get('sha256')} for j in state['jobs'] if j.get('parent_id')]}
    current=capture()
    assert len(current['topic'][0]['pregenerated_structure']['scenes'])==53
    missing=[s['scene_number'] for s in current['topic'][0]['pregenerated_structure']['scenes'] if not s.get('image_url')]
    assert missing==[21,22,23,24]
    report.update(verified_image_count=49,missing_scene_numbers=missing,verified_at=current['captured_at'])
    write(DEST/'final-review.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='final-review':final_review()
    elif sys.argv[1]=='event':
        state=recovery.update_file(recovery.state_path(MANIFEST),lambda s:recovery.transition(s,json.loads(sys.argv[2])))
        print(json.dumps({'ready':recovery.summary(state)['ready'],'attention':recovery.summary(state)['attention']}))
