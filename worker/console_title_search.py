"""Server-side search of displayed topic numbers and locally translated titles."""
import hashlib
import json
import re
from pathlib import Path

from worker.local_media_dashboard import _PREPARED_KO


def quoted(value):
    return json.dumps(str(value), ensure_ascii=False)


def topic_number(query):
    value = query.strip().removeprefix('#').strip()
    return str(int(value)) if re.fullmatch(r'\d{1,16}', value) else None


def translated_sources(query, root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1] / 'output/codex-local-console'
    translations = dict(_PREPARED_KO)
    for path in (root / 'title-translations').glob('*.json'):
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(saved, dict):
                continue
            source, ko = saved.get('source'), saved.get('ko')
            if isinstance(source, str) and isinstance(ko, str) and hashlib.sha256(source.encode('utf-8')).hexdigest() == path.stem:
                translations[source] = ko
        except (OSError, ValueError):
            continue
    term = ' '.join(query.casefold().split())
    return sorted(source for source, ko in translations.items() if term in ' '.join(ko.casefold().split())) if term else []


def exact_title_clauses(fields, sources):
    clauses = []
    for offset in range(0, len(sources), 40):
        values = ','.join(quoted(value) for value in sources[offset:offset + 40])
        clauses.extend(f'{field}.in.({values})' for field in fields)
    return clauses


def title_clauses(query, fields, sources):
    safe = query.strip().replace('*', '').replace('%', '').replace('_', '')
    return [f'{field}.ilike.{quoted("*" + safe + "*")}' for field in fields] + exact_title_clauses(fields, sources)


def catalog_filter(query, kind, root=None):
    fields = ['topic', 'generated_title'] if kind == 'topic' else ['title', 'employee_email']
    sources = translated_sources(query, root)
    clauses = title_clauses(query, fields, sources)
    number = topic_number(query)
    if number is not None:
        clauses.append(('id' if kind == 'topic' else 'topic_queue_id') + '.eq.' + number)
    return '(' + ','.join(clauses) + ')'


def read_all(store, table, clauses):
    rows = []
    offset = 0
    while True:
        batch, total = store.request('GET', table, params={'select': 'id', 'or': '(' + ','.join(clauses) + ')',
            'order': 'id', 'offset': offset, 'limit': 500})
        rows.extend(batch)
        if len(batch) < 500 or (total is not None and len(rows) >= total):
            break
        offset += 500
    return [str(row['id']) for row in rows]


def history_filter(query, store, root=None):
    sources = translated_sources(query, root)
    clauses = title_clauses(query, ['title'], sources)
    number = topic_number(query)
    topic_ids = [number] if number is not None else []
    if sources:
        topic_ids.extend(read_all(store, 'topics_queue', exact_title_clauses(['topic', 'generated_title'], sources)))
    topic_ids = sorted(set(topic_ids))
    project_clauses = []
    if sources:
        project_clauses.extend(exact_title_clauses(['title'], sources))
    for offset in range(0, len(topic_ids), 100):
        values = ','.join(topic_ids[offset:offset + 100])
        project_clauses.append(f'topic_queue_id.in.({values})')
        text_values = ','.join(quoted(value) for value in topic_ids[offset:offset + 100])
        clauses.append(f'and(source_kind.eq.topic,source_id.in.({text_values}))')
    project_ids = read_all(store, 'std_projects', project_clauses) if project_clauses else []
    for offset in range(0, len(project_ids), 100):
        values = ','.join(quoted(value) for value in project_ids[offset:offset + 100])
        clauses.append(f'and(source_kind.eq.project,source_id.in.({values}))')
    return '(' + ','.join(clauses) + ')'
