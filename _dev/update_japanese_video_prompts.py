import sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))
from dotenv import load_dotenv
for p in ['.env', '.env.local', 'auth-web/.env.local']:
    load_dotenv(ROOT / p)
from worker.script_worker_store import ScriptStore
from worker.codex_content_runner import CodexStagedContentRunner
from services.video_prompt_contract import VISIBLE_SPEECH_DIRECTION, VIDEO_AUDIO_GUARDS, silent_video_prompt

out = ROOT / '_dev/artifacts/japanese_video_prompt_revision'
out.mkdir(exist_ok=True)
store = ScriptStore()
runner = CodexStagedContentRunner()
for tid in [3376,3377,3378]:
    rows,_ = store.request('GET','topics_queue',params={'select':'*','id':f'eq.{tid}'})
    original = rows[0]
    (out/f'{tid}.before.json').write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf8')
    structure = copy.deepcopy(original['pregenerated_structure'])
    scenes = [s for s in structure['scenes'] if 1 <= int(s['scene_number']) <= 18]
    fields = ['scene_number','scene_text','scene_situation','scene_summary','characters_present','image_prompt']
    context = {'topic':original.get('topic'),'scenes':[{k:s.get(k) for k in fields} for s in scenes],'scene_cast':[c for c in structure.get('scene_cast',[]) if int(c['scene_number'])<=18]}
    result = runner._stage(f'prompt_revision_{tid}', '03_visible_speech_revision', context,
        'Write scene-specific English speaking instructions to append to existing video prompts. Existing character design/action/duration/style blocks will be preserved by the caller. Read actual scene_text and image_prompt to distinguish spoken dialogue from quoted letters or narration. '+VISIBLE_SPEECH_DIRECTION+
        ' Return {"scenes":[{"scene_number":1,"direction":"detailed speaking direction, 60-120 words", "speakers":["visible speaker name"],"reason":"brief Korean justification"}, ...]} covering exactly scene numbers 1 through 18. Never alter scripts or media or invent dialogue. Speaking direction must name the actual visible speaker and explain speech pauses/listeners/end pose for that specific scene; narration-only scenes explicitly mouths closed.')
    revisions = result['scenes']
    assert sorted(int(s['scene_number']) for s in revisions)==list(range(1,19))
    for rev in revisions:
        scene = next(s for s in structure['scenes'] if int(s['scene_number']) == int(rev['scene_number']))
        original_prompt = scene['video_prompt']
        prompt = silent_video_prompt(original_prompt)+'\n\nVisible speech direction: '+rev['direction']+'\nSilent output: no audible dialogue, '+', '.join(VIDEO_AUDIO_GUARDS)+'.'
        assert all(g in prompt.lower() for g in (*VIDEO_AUDIO_GUARDS,'no audible dialogue'))
        marker = 'recurring-character-designs-'
        if marker in original_prompt:
            design = original_prompt[original_prompt.index(marker):]
            assert design in prompt, 'Character block was changed'
        scene['video_prompt'] = prompt
    (out/f'{tid}.revision.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    projects,_ = store.request('GET','std_projects',params={'select':'id,topic_queue_id,project_payload','topic_queue_id':f'eq.{tid}'})
    assert not projects, 'Linked project exists; requires coordinated update'
    current,_ = store.request('GET','topics_queue',params={'select':'*','id':f'eq.{tid}'})
    assert current[0] == original, 'Topic changed during revision'
    params={'id':f'eq.{tid}', 'pregenerated_structure': 'eq.'+json.dumps(original['pregenerated_structure'],ensure_ascii=False,separators=(',',':'))}
    # JSON is too large for a URL predicate. Compare the server update timestamp instead.
    params.pop('pregenerated_structure')
    params['created_at']='eq.'+original['created_at']
    params['status']='eq.'+original['status']
    params['pregenerated_structure->scenes->0->>video_prompt']='eq.'+original['pregenerated_structure']['scenes'][0]['video_prompt']
    saved,_ = store.request('PATCH','topics_queue',params=params,body={'pregenerated_structure':structure},prefer='return=representation')
    assert len(saved)==1 and saved[0]['pregenerated_structure']==structure
    expected = copy.deepcopy(original)
    expected['pregenerated_structure']=structure
    assert all(saved[0].get(k)==v for k,v in expected.items() if k!='updated_at')
    print(json.dumps({'topic_id':tid,'updated':len(revisions),'speaking_scenes':[s['scene_number'] for s in revisions if s['speakers']]},ensure_ascii=False),flush=True)
