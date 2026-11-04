import hashlib
import json
import pytest
from scripts import restore_wuxia_handoff as restore


def snapshot(tmp_path, monkeypatch):
    root = tmp_path
    source = root/'docs/wuxia-handoff'
    episode = source/'episode-02'
    episode.mkdir(parents=True)
    data = json.dumps({'title':'돌아오는 검'}, ensure_ascii=False).encode('utf-8')
    (episode/'script-final.json').write_bytes(data)
    (source/'snapshot-manifest.json').write_text(json.dumps([{
        'episode':'episode-02', 'file':'script-final.json', 'bytes':len(data),
        'sha256':hashlib.sha256(data).hexdigest(),
    }]), encoding='utf-8')
    monkeypatch.setattr(restore, 'ROOT', root)
    monkeypatch.setattr(restore.sys, 'argv', ['restore', '--episode', '2'])
    return episode, root/'output/wuxia-series-rebuild/episode-02/script-final.json', data


def test_restore_is_unicode_exact_and_repeatable(tmp_path, monkeypatch):
    _, target, data = snapshot(tmp_path, monkeypatch)
    restore.main()
    restore.main()
    assert target.read_bytes() == data


def test_restore_rejects_corrupt_snapshot(tmp_path, monkeypatch):
    source, target, _ = snapshot(tmp_path, monkeypatch)
    (source/'script-final.json').write_bytes(b'changed')
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        restore.main()
    assert not target.exists()


def test_restore_preserves_existing_different_work(tmp_path, monkeypatch):
    _, target, _ = snapshot(tmp_path, monkeypatch)
    target.parent.mkdir(parents=True)
    target.write_bytes(b'newer user work')
    with pytest.raises(RuntimeError, match='Existing work differs'):
        restore.main()
    assert target.read_bytes() == b'newer user work'
