"""Offline invariants for the one-project approved visual revision."""
import copy
import json
import unittest
from scripts.publish_3197_approved_visuals import OUT, PID, build, PREFIX

class RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((OUT/'before.json').read_text(encoding='utf-8'))
        cls.prepared=json.loads((OUT/'prepared.json').read_text(encoding='utf-8'))
        names=[f'scenes/scene-{i:03d}.png' for i in range(1,54)]+[f'characters/{k}.png' for k in ('sunim','deoksu','mother','jang','bokdong')]+['thumbnail-background.png','thumbnail-final.png']
        cls.uploaded={n:{'url':f'https://example.test/{PREFIX}/{n}','path':f'{PREFIX}/{n}','sha256':'test-only','size':123} for n in names}

    def test_project_only_and_no_script_or_subtitle_edits(self):
        original=copy.deepcopy(self.before)
        ops,assets=build(self.before,self.prepared,self.uploaded)
        self.assertEqual(self.before,original)
        self.assertEqual({t for t,b,c in ops},{'std_projects','std_project_scenes','std_project_assets'})
        self.assertTrue(all(a['project_id']==PID for a in assets))
        editor=ops[-1][2]['project_payload']
        self.assertEqual(editor['script'],self.before['project']['project_payload']['script'])
        self.assertEqual([(s['id'],s['text']) for s in editor['subtitles']],[(s['id'],s['text']) for s in self.before['project']['project_payload']['subtitles']])
        self.assertEqual(len(assets),54)
        self.assertEqual(len({a['id'] for a in assets}),54)

    def test_every_scene_layer_matches_and_old_clips_not_active(self):
        ops,assets=build(self.before,self.prepared,self.uploaded)
        payload=ops[-1][2]
        def inspect(value):
            if isinstance(value,list):
                for v in value:inspect(v)
            elif isinstance(value,dict):
                self.assertFalse(value.get('video_url'))
                self.assertNotIn('video_asset_id',value)
                self.assertNotIn('retention_hook',value)
                if isinstance(value.get('scenes'),list) and value['scenes'] and 'image_prompt' in value['scenes'][0]:
                    self.assertEqual(len(value['scenes']),53)
                    for i,s in enumerate(value['scenes'],1):
                        self.assertEqual(s['image_prompt'],self.prepared['scenes'][i-1]['image_prompt'])
                        self.assertEqual(s['scene_text'],self.prepared['scenes'][i-1]['scene_text'])
                        self.assertEqual(s['video_prompt'],self.prepared['scenes'][i-1]['video_prompt'])
                        if s.get('metadata'): self.assertEqual(s['metadata']['scene_text'],s['scene_text'])
                for v in value.values():inspect(v)
        inspect(payload)
        self.assertEqual(sum(bool(c['video_prompt']) for t,b,c in ops if t=='std_project_scenes'),12)
        self.assertEqual(payload['project_payload']['main_character']['name'],'순임')
        self.assertEqual(len(payload['project_payload']['supporting_characters']),4)
        self.assertNotEqual(payload['project_payload']['thumbnail_design']['editor_bg_url'],payload['project_payload']['thumbnail_url'])

if __name__=='__main__':unittest.main()
