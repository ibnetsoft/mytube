"""Prepare and persist native portraits, then author scene prompts against them."""
import json, shutil
from pathlib import Path
from draft_3292_scoped import OUT, save
from codex_character_assets import CharacterAssetStore,digest
from codex_content_runner import CodexStagedContentRunner,CodexContentConfig

assert json.loads((OUT/'approved-final-quality.json').read_text(encoding='utf-8'))['passed']
source=Path('C:/Users/Pc/.codex/generated_images/01a07157-6d55-7753-8bdc-53780dd4ee46')
specs=[
 ('yeoni','연이','주인공','20','exec-21c261d2-39cb-4d7e-b30c-9c041fb16a70.png','Slightly broad oval Korean face, straight dark eyebrows, almond eyes, small rounded nose, warm skin; center parted black hair in one long unmarried braid, dark ribbon.','Ivory cotton jeogori, moss-green tie, rust-brown chima.'),
 ('sunduk','순덕','연이의 어머니','42','exec-e7dd7b12-ccfa-45cb-b9ed-25c7c92d0783.png','Long narrow Korean face, high cheekbones, downturned eyes, furrowed brow, weathered warm skin; black hair with sparse gray in low bun, wooden pin.','Faded dusty blue cotton jeogori, charcoal brown chima.'),
 ('geumrye','금례','순덕의 어머니·연이의 외할머니','68','exec-43124758-02d6-4f64-a9b9-46b01ededa54.png','Rounded square Korean face, broad cheeks, heavy eyelids, deep smile lines, small mole below left cheekbone; silver-gray low bun with wooden pin, sturdy frame.','Muted ochre brown cotton jeogori, dark indigo chima.')]
store=CharacterAssetStore(); portraits=OUT/'characters';portraits.mkdir(exist_ok=True)
anchors=[]
for key,name,role,age,file,dna,clothes in specs:
    target=portraits/(key+'.png')
    if not target.exists():shutil.copy2(source/file,target)
    character={'character_key':'3292-final-'+key,'name':name,'role':role,'gender':'female','age_group':age,
        'visual_dna_en':dna,'wardrobe_en':clothes,
        'continuity_instruction':'Keep identity, costume and age in present-day scenes. Only explicitly designated 30-year flashbacks de-age Geumrye to38 and Sunduk to12. Yeoni is not born in those flashbacks.',
        'image_prompt':'Photorealistic late Joseon Korean character reference portrait, one person, neutral clay backdrop, soft natural light, waist-up, no text or modern items. '+name+', age'+age+'. '+dna+' '+clothes}
    anchors.append(store.publish(3292,character,target,digest(character),{'category':'옛날이야기','image_style':'realistic'}))
    print('portrait saved and read back: '+name,flush=True)
save('character-anchors.json',{'main_character':anchors[0],'supporting_characters':anchors[1:],
    'max_character_anchors':3,'character_image_generation':{'status':'ready','count':3}})
c=json.loads((OUT/'candidate-final.json').read_text(encoding='utf-8'))
req=json.loads((OUT/'request.json').read_text(encoding='utf-8'))
r=CodexStagedContentRunner(CodexContentConfig.from_environment())
context={'title':req['title'],'sections':c['sections'],'schedule':req['schedule'],'character_anchors':anchors,
    'image_style':'realistic','style_prompt':'A highly realistic photo, lifelike textures, natural lighting, professional cinematography.',
    'other_cast':'Choi Seobang age50 narrow angular face sparse pointed moustache black topknot, dark plum silk robe. His father Choi Buja age50 in thirty-year flashbacks, broad heavy face full moustache, dark green silk robe, DIFFERENT person. Teacher age60 lean face gray beard, off-white robe and black scholar hat. Choi mother middle-aged woman in dull mauve jeogori, limited flashback41 only.',
    'prop':'The same small aged silver hoop earrings; one hoop has crescent-shaped solder repair INSIDE its ring, not a crescent-shaped dangling pendant. Gray-beige old jeogori with torn inner pocket and lining; two hoops lodge between lining and outer layer. All scenes late Joseon Korean rural village, no modern props.'}
print('authoring all 53 scene prompts',flush=True)
result=r._stage('3292_final_media','03_scene_prompts',context,
    'Return {scenes:[{scene_number:1,scene_summary:"Korean short label",image_prompt:"detailed English prompt",video_prompt:"...",characters_present:["names"],time_period:"present|flashback"}]}. Exactly53 ordered scenes. '
    'Preserve script and mapping; illustrate specific action in EACH supplied section. Opening twelve have still keyframes AND unique 5-second video prompts >=260 chars, with exactly one movement chosen from slow push-in, slow pull-back, gentle pan, gentle tilt, slow dolly, slow tracking shot, locked-off shot, subtle crane movement, slow drift. '
    'Every first12 video prompt must contain no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio. Later video_prompt empty. '
    'Reference stored character faces; key present ages20/42/68. Flashbacks17-24 and41 depict younger people, avoid elder face in past. Scene25 is later memory and26 inheritance; choose one precise moment and its proper ages. '
    'Do not invent visual actions unrelated to text. No legible overlay text, watermarks, western or modern objects. Each image prompt standalone with identity, age, costume, era, action, composition, lighting. Vary shots meaningfully. Do not generate images in this stage.')
assert len(result['scenes'])==53
from codex_content_runner import _validate_video_prompt
for i,s in enumerate(result['scenes'],1):
    assert s['scene_number']==i and len(s['image_prompt'])>120
    if i<=12:_validate_video_prompt(s['video_prompt'],i)
save('media-prompts.json',result)
print('53 media prompts saved',flush=True)
