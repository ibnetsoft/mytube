"""Indexed local Scripture/reference catalog; exact source files remain the authority."""
import json
import sqlite3
from pathlib import Path


class BibleLibrary:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'catalog.sqlite3', timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, title TEXT, locator TEXT, '
                        'translation TEXT, book TEXT, chapter INTEGER, verse_start INTEGER, verse_end INTEGER, metadata TEXT)')
        self.db.execute('CREATE INDEX IF NOT EXISTS source_passage ON sources(translation,book,chapter,verse_start,verse_end)')
        self.db.execute('CREATE TABLE IF NOT EXISTS library_metadata (key TEXT PRIMARY KEY)')
        if not self.db.execute("SELECT key FROM library_metadata WHERE key='migrated'").fetchone():
            for path in self.root.glob('*.json'):
                self.put(json.loads(path.read_text(encoding='utf-8')), commit=False)
            self.db.execute("INSERT INTO library_metadata VALUES ('migrated')")
        self.db.commit()

    def put(self, source, commit=True):
        metadata = {k: v for k, v in source.items() if k != 'text'}
        metadata['characters'] = len(source['text'])
        self.db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?,?)',
                        (source['id'], source['title'], source['locator'], source.get('translation', ''),
                         source.get('book', ''), source.get('chapter'), source.get('verse_start'), source.get('verse_end'),
                         json.dumps(metadata, ensure_ascii=False)))
        if commit:
            self.db.commit()

    def search(self, q='', translation='', book='', chapter=None, verse=None):
        terms, args = [], []
        for column, value in (('translation', translation), ('book', book), ('chapter', chapter)):
            if value is not None and value != '':
                terms.append(column + '=?')
                args.append(value)
        if verse is not None:
            terms.append('verse_start<=? AND verse_end>=?')
            args += [verse, verse]
        if q:
            # Literal substring matching, including % and _, without LIKE wildcard surprises.
            terms.append('(instr(lower(title),lower(?))>0 OR instr(lower(locator),lower(?))>0)')
            args += [q, q]
        where = ' WHERE ' + ' AND '.join(terms) if terms else ''
        total = self.db.execute('SELECT COUNT(*) FROM sources' + where, args).fetchone()[0]
        rows = self.db.execute('SELECT metadata FROM sources' + where +
                               ' ORDER BY book,chapter,verse_start,title,id LIMIT 1000', args).fetchall()
        return {'items': [json.loads(row[0]) for row in rows], 'total': total, 'limited': total > len(rows)}

    def close(self):
        self.db.close()
