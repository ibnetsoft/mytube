"""Project-local visual plan from the approved script; no database writes."""
import copy, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.audit_active_content import fetch
from scripts.repair_active_materials import dump

OUT=ROOT/'output/3197_approved_visual_revision'
PID='10b3d223-1457-415a-ba40-7b947c6c1b3d'
STYLE='Photorealistic live-action Korean historical drama, rural late Joseon, natural skin pores and worn hemp/cotton fabric, cinematic but restrained natural lighting, authentic wooden houses and dirt paths. Landscape 16:9. No animation, illustration, modern objects, text overlays, captions, logos or watermarks.'
DNA={
'sunim':'Sunim, Korean woman 35, refined oval face, weathered pale skin, calm resilient dark eyes, black hair in a neat low bun, unbleached cotton jeogori and charcoal grey chima. Preserve face from reference 2.',
'deoksu':'Deoksu, Korean man 38, weathered strong jaw, dark eyes, short moustache and goatee, black topknot, unbleached cotton hanbok with dark indigo working vest. Preserve face from reference 1.',
'mother':'Mother-in-law, Korean woman 68, deeply lined face, thin silver-grey hair in low bun, pale grey jeogori and dark navy chima. Preserve face from reference 3.',
'jang':'Jang, Korean man 70, deeply lined long face, white eyebrows, short white beard, white hair under cream cotton headband, rough brown hemp jacket and trousers, cloth shoulder bag. Preserve reference 4.',
'bokdong':'Bokdong, Korean boy 10, slim frame, round gentle face, black fringe and single braid, faded dusty blue jeogori and unbleached trousers. Preserve reference 5. Never depict as an adult.',
'father':'Father-in-law in the past, Korean man 65, broad lined face resembling Deoksu, neat grey topknot and short grey beard, plain off-white hanbok and light brown vest. No white headband; distinct from Jang.',
'baek':'Baek, Korean merchant 45 in the past, heavy square face, narrow calculating eyes, trimmed black moustache, black gat, dark olive silk outer robe over pale hanbok. Distinct from Deoksu and Jang.'}

def main():
    p=fetch('std_projects',id='eq.'+PID)[0]
    assert p['status']=='in_progress' and not p.get('submitted_at')
    script=p['project_payload']['script']; sha=hashlib.sha256(script.encode()).hexdigest()
    assert sha=='b6a1ae235bb5025c4826130123071e6360dc3989156e233ef713c723368a7658'
    rows=fetch('std_project_scenes',project_id='eq.'+PID,order='scene_number.asc')
    assets=fetch('std_project_assets',project_id='eq.'+PID,order='id.asc')
    plan=json.loads((ROOT/'docs/script-revisions/3197-visual-scenes.json').read_text(encoding='utf-8'))
    assert len(plan)==len(rows)==53
    dump(OUT/'before.json',{'project':p,'scenes':rows,'assets':assets})
    scenes=[]
    movements=['slow tracking shot','slow push-in','locked-off shot','slow push-in','gentle tilt','slow push-in','slow push-in','locked-off shot','gentle tilt','slow push-in','locked-off shot','gentle pan']
    for i,(cast,period,action) in enumerate(plan,1):
        age=''
        if period=='past':age='FLASHBACK TEN YEARS EARLIER: Sunim is 25, Deoksu 28, mother-in-law 58, Jang 60. Preserve their facial identity but reduce age lines and grey hair. Include only the people and objects explicitly specified in this shot. '
        elif period=='middle':age='EXILE YEARS between past and present: Sunim is about 30. Preserve face with fewer age lines. Any child is about five, never the present ten-year-old. '
        elif period=='recentwinter':age='WINTER shortly before present: Sunim is 35; worn outer shawl is appropriate. '
        prompt=' '.join([STYLE,age,action,'Cast identity: '+ ' '.join(DNA[c] for c in cast.split(','))])
        video=''
        if i<=12:
            video=(f'One continuous 5-second image-to-video shot from the matching scene still. {action} '
                f'Preserve the exact faces, costumes, object positions and lighting of the input image. '
                f'Only one restrained action from this beat, natural blinking and breathing; no scene transition or new objects. '
                f'Camera movement: {movements[i-1]}. no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio.')
        scenes.append({'scene_number':i,'scene_order':i,'scene_text':rows[i-1]['scene_text'],'image_prompt':prompt,'video_prompt':video,'period':period,'cast':cast.split(',')})
    refs=[str(ROOT/f'output/3197_visual_revision/character-reference-{i}.png') for i in [1,2,3]]+[str(OUT/'character-jang.png'),str(OUT/'character-bokdong.png')]
    grids=[]
    for start in range(0,53,4):
        numbers=list(range(start+1,min(start+5,54)))
        if len(numbers)<4:numbers=[50,51,52,53]
        instruction='Create ONE landscape 16:9 image consisting of an exact seamless 2x2 grid of FOUR equal 16:9 film stills. Panel order top-left, top-right, bottom-left, bottom-right. Divide exactly at horizontal and vertical halfway; NO borders, gutters, labels or text. Every panel is a different specified shot. Photorealistic live-action, not illustration. Reference images in order: 1 Deoksu, 2 Sunim, 3 mother-in-law, 4 Jang, 5 Bokdong. Match named faces but include ONLY the cast specified in each panel. Honor flashback ages. No objects from other panels.\n'
        instruction+='\n'.join(f'{pos} PANEL (scene {n}): {scenes[n-1]["image_prompt"]}' for pos,n in zip(['TOP LEFT','TOP RIGHT','BOTTOM LEFT','BOTTOM RIGHT'],numbers))
        grids.append({'grid_number':len(grids)+1,'scene_numbers':numbers,'prompt':instruction,'raw_file':f'grid-{len(grids)+1:03d}.png'})
    metadata={'title':p['title'],'description':'십 년 전, 순임은 자신이 살려 낸 조카 때문에 거짓 소문에 휘말려 마을에서 쫓겨났습니다. 남편마저 등을 돌린 뒤, 바느질로 아이를 키우며 버틴 세월. 이제 순임은 해진 보따리 하나를 들고 돌아옵니다. 그 안에 간직한 은가락지와 시아버지의 글은 무엇을 말해 줄까요? 누명을 벗는 일과 상처 입은 관계를 다시 세우는 일은 같은 속도로 이루어지지 않습니다. 순임과 복동, 그리고 뒤늦게 자기 잘못을 마주하는 가족의 이야기를 들려드립니다.\n\n이 영상은 창작한 옛날이야기이며, 실제 인물이나 사건을 다룬 실화가 아닙니다.',
        'tags':['옛날이야기','창작설화','며느리','보따리','가족이야기','누명','순임','복동'],
        'hashtags':['#옛날이야기','#창작이야기','#가족이야기'],
        'thumbnail_hook_texts':['십 년 만에 돌아온 며느리','제 이름을 찾으러 왔습니다','보따리에 간직한 진실']}
    thumb_prompt=STYLE+' One full-frame YouTube thumbnail background, NOT a grid. Sunim fills the right half, holding a small opened hemp bundle at waist height with one plain silver ring and a folded old letter visible. Her composed determined face, not screaming. Mother-in-law in soft focus by the old gate farther behind. Soft warm directional daylight, high clarity. The left lower half is darker simple weathered wood with empty space for later Korean headline, no embedded text. Keep the faces of references 2 and 3. No white stones, red string, severed hair, coffins, well, modern props or piles of money.'
    package={'project_id':PID,'script_sha256':sha,'scenes':scenes,'image_grid_prompts':grids,'cast_dna':DNA,'publish_metadata':metadata,'thumbnail_prompt':thumb_prompt,'thumbnail_texts':['십 년 만에 돌아온 며느리','제 이름을 찾으러 왔습니다']}
    dump(OUT/'prepared.json',package)
    dump(OUT/'manifest.json',{'schema':'cowork_scene_assets/v1','topic_id':'3197','project_id':PID,'title':p['title'],'bucket':'content-assets','scene_count':53,'script_sha256':sha,'grids':grids,'reference_paths':refs})
    print(json.dumps({'scenes':len(scenes),'video_prompts':sum(bool(s['video_prompt']) for s in scenes),'grids':len(grids),'script_sha256':sha}))

if __name__=='__main__':main()
