from types import SimpleNamespace

import pytest
from PIL import Image

from worker import cowork_thumbnail_asset as thumbnail
from worker import gcs_media_storage as storage


def test_thumbnail_uses_gcs_and_only_text_metadata_goes_to_supabase(monkeypatch, tmp_path):
    image = tmp_path / "background.png"
    Image.new("RGB", (32, 18), "white").save(image)
    monkeypatch.setattr(thumbnail, "_topic", lambda _: ({"id": 123, "progress_payload": {}}, "https://db.example", {}))
    uploaded, writes = [], []
    url = "/api/std/assets/gcs-file?bucket=b&path=thumbnail.png"
    monkeypatch.setattr(thumbnail, "_upload_gcs_file", lambda file, path, mime: (uploaded.append((file, path, mime)) or ("b", path, url)))
    monkeypatch.setattr(thumbnail.requests, "post", lambda *a, **k: pytest.fail("No Supabase Storage uploads or bucket creation"))
    monkeypatch.setattr(thumbnail.requests, "patch", lambda endpoint, **kwargs: (writes.append((endpoint, kwargs["json"])) or SimpleNamespace(status_code=204)))
    monkeypatch.setattr(thumbnail, "_sync_claimed_std_projects", lambda *args: None)
    assert thumbnail.publish("123", image, create_bucket=True) == url
    assert len(uploaded) == 1 and uploaded[0][2] == "image/png"
    assert writes[0][0].startswith("https://db.example/rest/v1/topics_queue")
    assert writes[0][1]["progress_payload"]["thumbnail_bg_url"] == url


def test_gcs_failure_never_falls_back_to_supabase(monkeypatch, tmp_path):
    image = tmp_path / "background.png"
    Image.new("RGB", (32, 18), "white").save(image)
    monkeypatch.setattr(thumbnail, "_topic", lambda _: ({"id": 123}, "https://db.example", {}))
    def fail(*args):
        raise RuntimeError("GCS unavailable")
    monkeypatch.setattr(thumbnail, "_upload_gcs_file", fail)
    monkeypatch.setattr(thumbnail.requests, "post", lambda *a, **k: pytest.fail("No storage fallback"))
    monkeypatch.setattr(thumbnail.requests, "patch", lambda *a, **k: pytest.fail("No database update without a file"))
    with pytest.raises(RuntimeError, match="GCS unavailable"):
        thumbnail.publish("123", image)


def test_gcs_uploader_posts_binary_only_to_google(monkeypatch, tmp_path):
    file = tmp_path / "image.png"
    file.write_bytes(b"image fixture")
    monkeypatch.setattr(storage, "_gcs_credentials", lambda: (SimpleNamespace(token="fixture"), "bucket"))
    def post(url, **kwargs):
        assert url.startswith("https://storage.googleapis.com/upload/storage/v1/b/bucket/o?")
        assert kwargs["data"].read() == b"image fixture"
        return SimpleNamespace(status_code=200)
    monkeypatch.setattr(storage.requests, "post", post)
    bucket, path, url = storage._upload_gcs_file(file, "topics/123/image.png", "image/png")
    assert bucket == "bucket" and path == "topics/123/image.png"
    assert url.startswith("/api/std/assets/gcs-file?")
