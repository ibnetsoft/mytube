import pytest
from worker.production_engine_policy import alternatives_enabled, require_engine

def test_alternative_engines_are_blocked_but_ae_and_ffmpeg_work():
    assert alternatives_enabled() is False
    require_engine('ae', 'python')
    require_engine('webtoon')
    for engine in ('effectcraft', 'filmcraft', 'motion_studio'):
        with pytest.raises(ValueError): require_engine(engine)
    with pytest.raises(ValueError): require_engine('ae', 'filmcraft')

def test_supervisor_rejects_direct_alternative_launch():
    from worker.local_media_supervisor import role_command
    for role in ('effectcraft', 'filmcraft'):
        with pytest.raises(ValueError): role_command(role)
    assert '--engine' in role_command('motion_automation')
