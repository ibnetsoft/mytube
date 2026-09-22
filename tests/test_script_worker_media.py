from worker.script_worker_media import media_summary, image_url, thumbnail
from worker.script_worker_store import ScriptStore, StoreUnavailable


def test_prompts_and_character_dna_are_not_generated_images():
    result = media_summary({'structure': {'main_character': {'name': '주인공', 'image_prompt': 'portrait'},
        'scenes': [{'image_prompt': 'landscape'}, {'image_prompt': 'street'}]}})
    assert result['characters'] == {'status': 'not_started', 'count': 0, 'total': 1}
    assert result['images'] == {'status': 'not_started', 'count': 0, 'total': 2}


def test_character_registry_matches_plan_and_ignores_unrelated_old_character():
    result = media_summary({'structure': {'main_character': {'name': '주인공', 'character_key': 'hero'},
        'supporting_characters': [{'name': '친구', 'character_key': 'friend'}],
        'scenes': [{'image_url': 'https://example.com/1.png'}, {}]}}, registry=[
        {'name': '주인공', 'character_key': 'hero', 'image_url': 'https://example.com/hero.png'},
        {'name': '삭제된 인물', 'character_key': 'old', 'image_url': 'https://example.com/old.png'}])
    assert result['characters'] == {'status': 'partial', 'count': 1, 'total': 2}
    assert result['images'] == {'status': 'partial', 'count': 1, 'total': 2}


def test_ready_without_image_links_is_not_completed():
    result = media_summary({'structure': {'character_reference_status': 'ready', 'main_character': {'name': 'a'}}})
    assert result['characters']['status'] == 'unverified'
    failed = media_summary({'structure': {'scenes': [{'image_generation_status': 'failed'}]}})
    assert failed['images']['status'] == 'failed'
    running = media_summary({'structure': {'scenes': [{}]}}, {'image_generation_status': 'generating'})
    assert running['images']['status'] == 'running'


def test_final_thumbnail_wins_over_background_and_unsafe_urls_are_rejected():
    assert thumbnail({'thumbnail_bg_url': 'https://example.com/bg.png'},
                     {'thumbnail_url': 'https://example.com/final.png'})['label'] == '썸네일'
    for unsafe in ['javascript:alert(1)', 'file:///C:/secret', '//example.com/x', 'https://user:pass@example.com/a']:
        assert image_url(unsafe) == ''


def test_history_batches_media_and_does_not_use_original_images_for_new_candidate(monkeypatch):
    store = ScriptStore()
    calls = []
    identity = 'a' * 32
    def fake(method, table, **kw):
        calls.append(table)
        return {
            'topics_queue': [{'id': 42, 'pregenerated_structure': {'scenes': [{'image_url': 'https://example.com/scene.png'}]}}],
            'topic_character_assets': [{'topic_queue_id': 42, 'name': 'hero', 'image_url': 'https://example.com/hero.png'}],
            'std_projects': [{'id': 'p', 'topic_queue_id': 42, 'project_payload': {'thumbnail_bg_url': 'https://example.com/thumb.png'}}],
            'script_worker_jobs': [{'id': identity, 'candidate': {'structure': {'scenes': [{}]}}}],
        }[table], None
    monkeypatch.setattr(store, 'request', fake)
    rows = [{'origin': 'legacy', 'id': str(i), 'source_id': '42', 'source_kind': 'topic', 'title': '이야기', 'job_type': 'script_generate'} for i in range(3)]
    rows.append({'origin': 'dedicated', 'id': identity, 'source_id': '42', 'source_kind': 'topic'})
    store.enrich_media(rows)
    assert len(calls) == 4
    assert rows[0]['media']['characters']['count'] == 1
    assert rows[0]['media']['images']['status'] == 'ready'
    assert rows[0]['media']['thumbnail']['label'] == '연결 프로젝트 · 썸네일 배경'
    assert rows[-1]['media']['images']['count'] == 0
    assert rows[-1]['media']['thumbnail']['url'] == ''


def test_missing_media_query_does_not_claim_not_generated(monkeypatch):
    store = ScriptStore()
    def fail(*args, **kwargs):
        raise StoreUnavailable('offline')
    monkeypatch.setattr(store, 'request', fail)
    rows = [{'origin': 'legacy', 'id': 'old', 'source_kind': 'topic', 'source_id': '42'}]
    store.enrich_media(rows)
    assert rows[0]['media']['images']['status'] == 'unknown'
    assert rows[0]['media']['basis'] == '미디어 조회 실패'
