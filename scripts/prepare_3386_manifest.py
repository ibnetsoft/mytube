"""Prepare 3386 image manifest with the user's current face-review preference."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'worker')]
import worker_config
from worker import cowork_scene_assets

if __name__ == '__main__':
    path = ROOT / 'output/codex-local-console/d57947df4af3479b85185c7ca0610a60/actual-production/manifest.json'
    original = cowork_scene_assets._topic
    def with_truthful_quality_notes(topic_id):
        row, structure, base, headers = original(topic_id)
        if str(topic_id) != '3386':
            raise ValueError('토픽이 변경됐습니다.')
        structure['continue_on_face_quality_notes'] = True
        # 2026-11-01: user explicitly stopped face comparisons for this job.
        # Saved reference identities remain authoritative; no pass is claimed.
        structure['skip_face_identity_review'] = True
        return row, structure, base, headers
    cowork_scene_assets._topic = with_truthful_quality_notes
    print(cowork_scene_assets.export_manifest('3386', path, cowork_scene_assets.DEFAULT_BUCKET))
