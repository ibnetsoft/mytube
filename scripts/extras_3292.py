"""Author annotations and metadata, preserve final narration exactly."""
import json
from draft_3292_scoped import OUT,save
from codex_content_runner import CodexStagedContentRunner,CodexContentConfig
from codex_dialogue import DIALOGUE_TASK,validate_dialogue
s=json.loads((OUT/'staged-structure.json').read_text(encoding='utf-8'))
r=CodexStagedContentRunner(CodexContentConfig.from_environment())
ctx={'title':'떨어진 귀걸이가 부른 일, 그 집안 3대에 걸친 저주','scenes':s['scenes'],
    'cast':json.loads((OUT/'candidate-final.json').read_text(encoding='utf-8'))['characters']}
print('dialogue annotation',flush=True)
d=r._stage('3292_final_extras','02e_dialogue',ctx,DIALOGUE_TASK)
save('dialogue-annotations.json',validate_dialogue(d,s['scenes']))
print('metadata',flush=True)
m=r._stage('3292_final_extras','04_publish_metadata',{'title':ctx['title'],'sections':[{'scene_order':x['scene_order'],'text':x['scene_text']} for x in s['scenes']]},
    'Return {description:"Korean honest engaging description 300-600 chars, disclose 창작 옛날이야기",tags:[15 Korean strings],hashtags:[5],thumbnail_text:"short Korean text",thumbnail_background_prompt:"English text-free 16:9 photographic composition matching exact story, main3 faces from refs, earring small not giant",titles:[original title]}. No unrelated graveside story, no claim true historical event, no invented twist or plot. Keep original title.')
save('publish-metadata.json',m)
print('extras saved',flush=True)
