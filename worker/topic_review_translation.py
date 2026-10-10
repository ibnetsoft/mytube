"""Local Codex review translation. Source briefs and approval data stay unchanged."""
import hashlib
import json
import threading
from pathlib import Path

from worker.codex_subtitle_translation import translate_blocks

FIELDS = ('title', 'story', 'character_notes', 'requirements', 'setting_country', 'era_region', 'transcript')
_lock = threading.RLock()
_tasks = {}


def translate_review(source, runner, identity):
    blocks, mapping = [], []
    for field in FIELDS:
        value = source.get(field) or ''
        for offset in range(0, len(value), 3000):
            mapping.append(field)
            blocks.append({'index': len(blocks), 'source_text': value[offset:offset + 3000]})
    translated = translate_blocks(runner, identity, blocks, 'ko')
    result = {field: '' for field in FIELDS}
    for block, field in zip(translated, mapping):
        result[field] += ('\n' if result[field] else '') + block['translated_text']
    return result


def request_review(row, jobs):
    brief = row['request_data']
    source = {field: str((row['title'] if field == 'title' else brief.get(field)) or '') for field in FIELDS}
    digest = hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    path = Path(jobs.root) / 'topic-review-translations' / (digest + '.json')
    with _lock:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if all(isinstance(data.get(field), str) and (not source[field] or data[field].strip()) for field in FIELDS):
                    return {'status': 'completed', 'translation': data}
            except (OSError, ValueError):
                pass
        future = _tasks.get(digest)
        if future and future.done():
            try:
                return {'status': 'completed', 'translation': future.result()}
            except Exception:
                _tasks.pop(digest, None)
                return {'status': 'failed', 'error': '로컬 Codex 한국어 번역에 실패했습니다. 다시 시도해 주세요.'}
        if not future:
            def run():
                from worker.codex_content_runner import CodexStagedContentRunner
                result = translate_review(source, CodexStagedContentRunner(), 'review-' + row['id'])
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
                temporary.replace(path)
                return result
            _tasks[digest] = jobs.pool.submit(run)
        return {'status': 'running'}
