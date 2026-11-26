from worker import codex_local_workflow, script_guidelines, script_worker_guidance


def test_production_guidance_includes_japanese_category_guide():
    guidance = script_worker_guidance.load_production_guidance()
    assert '다섯 카테고리 공통 대본 제작 기준' in guidance
    assert '작품마다 확정할 항목' in guidance
    assert '무협 웹툰 (ID 18)' in guidance
    assert '무협 연작의 회차 완료와 재개' in guidance
    assert '등록 → 저장 재조회' in guidance


def test_new_work_receives_local_guidance_without_changing_other_modes(monkeypatch):
    captured = []
    monkeypatch.setattr(script_guidelines, 'approved_guidelines', lambda *_: ([], ''))
    monkeypatch.setattr(script_worker_guidance, 'load_production_guidance', lambda: 'TEST OPERATING GUIDE')
    monkeypatch.setattr(codex_local_workflow, '_produce', lambda _id, request, *_: captured.append(request) or {})
    monkeypatch.setattr('worker.elevenlabs_performance.annotate_new_package', lambda package, *_: package)
    codex_local_workflow.produce('a', {'mode': 'new'}, None, None, lambda _: None)
    codex_local_workflow.produce('b', {'mode': 'topics'}, None, None, lambda _: None)
    assert 'TEST OPERATING GUIDE' in captured[0]['_approved_guidance']
    assert 'TEST OPERATING GUIDE' not in captured[1]['_approved_guidance']


def test_web_delivery_document_is_loaded_in_full():
    document = script_worker_guidance.WEB_DELIVERY_PATH.read_text(encoding='utf-8').strip()
    guidance = script_worker_guidance.load_production_guidance()
    assert document in guidance
    assert 'script_worker_web_delivery/v1' in guidance
    assert '실제 로그인된 유저웹' in document


def test_empty_web_delivery_document_does_not_silently_skip_guidance(monkeypatch, tmp_path):
    import pytest
    empty = tmp_path / 'delivery.md'
    empty.write_text('', encoding='utf-8')
    monkeypatch.setattr(script_worker_guidance, 'WEB_DELIVERY_PATH', empty)
    with pytest.raises(ValueError, match='유저웹 등록 작업 지침'):
        script_worker_guidance.load_production_guidance()
