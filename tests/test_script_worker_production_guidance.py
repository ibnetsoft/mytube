from worker import codex_local_workflow, script_guidelines, script_worker_guidance


def test_production_guidance_includes_japanese_category_guide():
    guidance = script_worker_guidance.load_production_guidance()
    assert '다섯 카테고리 공통 대본 제작 기준' in guidance
    assert '작품마다 확정할 항목' in guidance
    assert '무협 웹툰 (ID 18)' in guidance


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
