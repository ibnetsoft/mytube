"""Resumable upload behavior for the final Premiere MP4."""
from __future__ import annotations

import pathlib
import sys

import pytest
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))


class Response:
    def __init__(self, status_code, *, headers=None, metadata=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._metadata = metadata or {}
        self.text = text

    def json(self):
        return self._metadata


def test_final_upload_recovers_committed_chunk_after_lost_response(monkeypatch, tmp_path):
    import premiere_final_worker as worker

    content = b"a" * (8 * 1024 * 1024) + b"b" * 17
    source = tmp_path / "final.mp4"
    source.write_bytes(content)
    session_url = "https://storage.googleapis.com/upload/storage/v1/b/bucket/o?upload_id=abc"
    monkeypatch.setattr(worker, "_gcs_credentials", lambda: (type("Creds", (), {"token": "token", "expired": False})(), "bucket"))
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(worker.requests, "post", lambda *_args, **_kwargs: Response(200, headers={"Location": session_url}))
    calls = []

    def put(_url, *, headers, data, **_kwargs):
        calls.append((headers["Content-Range"], len(data)))
        if len(calls) == 1:
            raise requests.Timeout("response lost after GCS received chunk")
        if len(calls) == 2:
            return Response(308, headers={"Range": f"bytes=0-{8 * 1024 * 1024 - 1}"})
        return Response(200, metadata={"bucket": "bucket", "name": "final/video.mp4", "size": str(len(content))})

    monkeypatch.setattr(worker.requests, "put", put)
    bucket, path, url = worker._upload_gcs_file(source, "final/video.mp4", "video/mp4")
    assert (bucket, path) == ("bucket", "final/video.mp4")
    assert url.endswith("path=final%2Fvideo.mp4")
    assert calls == [
        (f"bytes 0-{8 * 1024 * 1024 - 1}/{len(content)}", 8 * 1024 * 1024),
        (f"bytes */{len(content)}", 0),
        (f"bytes {8 * 1024 * 1024}-{len(content) - 1}/{len(content)}", 17),
    ]
    assert not worker._gcs_upload_session_path(source, bucket, path).exists()


def test_final_upload_resumes_saved_session_after_worker_restart(monkeypatch, tmp_path):
    import premiere_final_worker as worker

    source = tmp_path / "final.mp4"
    source.write_bytes(b"0123456789abcdef")
    session_url = "https://storage.googleapis.com/upload/storage/v1/b/bucket/o?upload_id=restart"
    monkeypatch.setattr(worker, "_gcs_credentials", lambda: (type("Creds", (), {"token": "token", "expired": False})(), "bucket"))
    monkeypatch.setattr(worker.time, "sleep", lambda _seconds: None)
    starts = []

    def post(*_args, **_kwargs):
        starts.append(1)
        return Response(200, headers={"Location": session_url})

    monkeypatch.setattr(worker.requests, "post", post)

    def failing_put(_url, *, headers, **_kwargs):
        if headers["Content-Range"].startswith("bytes 0-"):
            raise requests.Timeout("network lost")
        return Response(503, text="temporary outage")

    monkeypatch.setattr(worker.requests, "put", failing_put)
    with pytest.raises(worker.GcsTransientUploadError, match="after 5 attempts"):
        worker._upload_gcs_file(source, "final/video.mp4", "video/mp4")
    sidecar = worker._gcs_upload_session_path(source, "bucket", "final/video.mp4")
    assert sidecar.is_file()

    ranges = []

    def resumed_put(_url, *, headers, data, **_kwargs):
        ranges.append(headers["Content-Range"])
        if len(ranges) == 1:
            return Response(308, headers={"Range": "bytes=0-3"})
        assert data == b"456789abcdef"
        return Response(200, metadata={"bucket": "bucket", "name": "final/video.mp4", "size": "16"})

    monkeypatch.setattr(worker.requests, "put", resumed_put)
    worker._upload_gcs_file(source, "final/video.mp4", "video/mp4")
    assert starts == [1]
    assert ranges == ["bytes */16", "bytes 4-15/16"]
    assert not sidecar.exists()


def test_final_upload_rejects_wrong_object_metadata(monkeypatch, tmp_path):
    import premiere_final_worker as worker

    source = tmp_path / "final.mp4"
    source.write_bytes(b"video")
    session_url = "https://storage.googleapis.com/upload/storage/v1/b/bucket/o?upload_id=wrong"
    monkeypatch.setattr(worker, "_gcs_credentials", lambda: (type("Creds", (), {"token": "token", "expired": False})(), "bucket"))
    monkeypatch.setattr(worker.requests, "post", lambda *_args, **_kwargs: Response(200, headers={"Location": session_url}))
    monkeypatch.setattr(worker.requests, "put", lambda *_args, **_kwargs: Response(200, metadata={"size": "2"}))
    with pytest.raises(worker.PremiereWorkerError, match="unexpected object size"):
        worker._upload_gcs_file(source, "final/video.mp4", "video/mp4")
