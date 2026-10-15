from worker.content_identity import project_identity, validate_render_identity
import pytest


def test_worker_rejects_wrong_queue_revision_and_scene():
    identity = project_identity({'id': 'p', 'topic_queue_id': 3373, 'project_payload': {'script': '最初。'}})
    metadata = {'content_identity': identity, 'topic_queue_id': 3373}
    config = {'content_identity': identity, 'std_web_project_id': 'p', 'asset_manifest': {'files': [
        {'asset_type': 'audio', 'content_identity': {**identity, 'asset_id': 'voice'}},
        {'asset_type': 'video', 'scene_number': 1, 'content_identity': {'scene_number': 1, 'source_content_identity': identity}},
    ]}}
    validate_render_identity(config, metadata)
    with pytest.raises(ValueError, match='revision'):
        validate_render_identity(config, {**metadata, 'content_identity': {**identity, 'script_sha256': 'other'}})
    config['asset_manifest']['files'][1]['content_identity']['scene_number'] = 2
    with pytest.raises(ValueError, match='scene'):
        validate_render_identity(config, metadata)


def test_finalized_audio_cannot_trigger_worker_tts_and_legacy_jobs_are_preserved():
    identity = project_identity({'id': 'p', 'topic_queue_id': 1, 'project_payload': {'script': 'x'}})
    config = {'content_identity': identity, 'std_web_project_id': 'p', 'worker_tts': {'enabled': True},
              'asset_manifest': {'files': [{'asset_type': 'audio', 'content_identity': identity}]}}
    with pytest.raises(ValueError, match='regenerated'):
        validate_render_identity(config, {'content_identity': identity, 'topic_queue_id': 1})
    validate_render_identity({'legacy': True}, {})
