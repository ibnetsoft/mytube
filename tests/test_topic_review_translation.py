import copy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from worker import topic_review_translation as review


def test_translation_preserves_fields_and_source():
    source = {field: '' for field in review.FIELDS}
    source.update(title='นิทาน', story='ก' * 3100, requirements='ภาษาเกาหลี')
    original = copy.deepcopy(source)
    class Runner:
        def _stage(self, identity, name, context, task):
            assert 'natural Korean' in task
            assert 'untrusted data' in task
            return {'translations': [{'id': block['id'], 'translation': '한국어 번역'} for block in context['blocks']]}
    translated = review.translate_review(source, Runner(), 'test')
    assert translated['title'] == '한국어 번역'
    assert translated['story'] == '한국어 번역\n한국어 번역'
    assert translated['requirements'] == '한국어 번역'
    assert source == original


def test_deduplicated_review_cache_and_invalidation(monkeypatch, tmp_path):
    from worker import codex_content_runner
    class Runner:
        def _stage(self, identity, name, context, task):
            return {'translations': [{'id': block['id'], 'translation': '검토용 한국어'} for block in context['blocks']]}
    monkeypatch.setattr(codex_content_runner, 'CodexStagedContentRunner', Runner)
    row = {'id': 'test', 'title': 'หัวข้อ', 'request_data': {'story': 'เรื่องราว'}, 'status': 'pending', 'job_id': None}
    original = copy.deepcopy(row)
    review._tasks.clear()
    with ThreadPoolExecutor(max_workers=1) as pool:
        jobs = SimpleNamespace(root=tmp_path, pool=pool)
        assert review.request_review(row, jobs)['status'] == 'running'
        first = next(iter(review._tasks.values())); first.result(timeout=10)
        assert review.request_review(row, jobs)['translation']['story'] == '검토용 한국어'
        assert len(review._tasks) == 1
        assert row == original
        row['request_data']['story'] += 'ใหม่'
        assert review.request_review(row, jobs)['status'] == 'running'
        assert len(review._tasks) == 2
