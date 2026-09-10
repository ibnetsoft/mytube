import json
from pathlib import Path

import services.remote_publish_service as remote_publish_module
from services.auto_publish_service import AutoPublishService
from services.remote_publish_service import RemotePublishService


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self.payload


def test_claim_is_atomic_and_records_publish_owner(monkeypatch):
    calls = []

    def fake_patch(table, payload, *, params, timeout):
        calls.append((table, payload, params, timeout))
        return FakeResponse([{"id": "publish-1", **payload}])

    monkeypatch.setattr(remote_publish_module.web_admin_client, "supabase_patch", fake_patch)
    service = RemotePublishService("render-pc-1")
    claimed = service.claim_request({
        "id": "publish-1",
        "status": "approved",
        "metadata": {"project_id": 1000003340},
    })

    assert claimed["status"] == "to_be_published"
    assert claimed["metadata"]["publish_operation"] == "upload"
    assert claimed["metadata"]["publish_worker_id"] == "render-pc-1"
    assert calls[0][2] == {"id": "eq.publish-1", "status": "eq.approved"}


def test_remote_publisher_skips_local_project_requests(monkeypatch):
    rows = [
        {"id": "local-1", "status": "approved", "metadata": {"source": "desktop_project"}},
        {"id": "remote-1", "status": "approved", "metadata": {"source": "render_queue_admin_upload"}},
    ]
    monkeypatch.setattr(
        remote_publish_module.web_admin_client,
        "supabase_get",
        lambda *args, **kwargs: FakeResponse(rows),
    )

    request = RemotePublishService("render-pc-1").fetch_next_request()

    assert request["id"] == "remote-1"


def test_local_publisher_leaves_drive_bundle_requests_for_remote_worker():
    assert AutoPublishService._is_remote_worker_request({
        "metadata": {"source": "render_queue_admin_upload"},
    })
    assert AutoPublishService._is_remote_worker_request({
        "metadata": {"upload_source": "remote_drive_bundle"},
    })
    assert not AutoPublishService._is_remote_worker_request({
        "metadata": {"source": "desktop_project"},
    })


def test_uploads_drive_bundle_without_local_project(monkeypatch, tmp_path):
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    token_file = token_dir / "token_1.pickle"
    token_file.write_bytes(b"token")
    monkeypatch.setattr(remote_publish_module.config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        remote_publish_module.db,
        "get_channel",
        lambda channel_id: {
            "id": channel_id,
            "name": "Honjada",
            "credentials_path": "tokens/token_1.pickle",
            "proxy": None,
        },
    )
    monkeypatch.setattr(
        remote_publish_module.google_drive_service,
        "read_text_file",
        lambda file_id: json.dumps({
            "title": "Drive title",
            "description": "Drive description",
            "tags": ["story", "folktale"],
        }),
    )

    def fake_download(file_id, destination):
        Path(destination).write_bytes(b"asset")
        return destination

    monkeypatch.setattr(remote_publish_module.google_drive_service, "download_file", fake_download)
    upload_calls = []
    thumbnail_calls = []
    monkeypatch.setattr(
        remote_publish_module.youtube_upload_service,
        "upload_video",
        lambda **kwargs: upload_calls.append(kwargs) or {"id": "youtube-123"},
    )
    monkeypatch.setattr(
        remote_publish_module.youtube_upload_service,
        "set_thumbnail",
        lambda **kwargs: thumbnail_calls.append(kwargs) or {},
    )

    request_updates = []

    def fake_patch(table, payload, *, params, timeout):
        request_updates.append((table, payload, params))
        return FakeResponse([{"id": "publish-1", **payload}])

    monkeypatch.setattr(remote_publish_module.web_admin_client, "supabase_patch", fake_patch)
    monkeypatch.setattr(
        remote_publish_module.web_admin_client,
        "supabase_get",
        lambda *args, **kwargs: FakeResponse([]),
    )

    service = RemotePublishService("render-pc-1")
    result = service.process_claimed_request({
        "id": "publish-1",
        "status": "to_be_published",
        "metadata": {
            "project_id": 1000003340,
            "publish_operation": "upload",
            "channel_id": 1,
            "drive_video_file_id": "drive-video",
            "drive_video_file_name": "result.mp4",
            "drive_thumbnail_file_id": "drive-thumbnail",
            "drive_thumbnail_file_name": "thumbnail.png",
            "drive_metadata_file_id": "drive-metadata",
            "privacy_status": "private",
        },
    })

    assert result == {
        "status": "published",
        "video_id": "youtube-123",
        "url": "https://youtu.be/youtube-123",
    }
    assert upload_calls[0]["title"] == "Drive title"
    assert upload_calls[0]["privacy_status"] == "private"
    assert upload_calls[0]["token_path"] == str(token_file)
    assert thumbnail_calls[0]["video_id"] == "youtube-123"
    assert request_updates[0][0] == "publishing_requests"
    assert request_updates[0][1]["status"] == "published"
    assert request_updates[0][1]["metadata"]["upload_source"] == "remote_drive_bundle"


def test_public_release_uses_same_assigned_channel(monkeypatch, tmp_path):
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    token_file = token_dir / "token_1.pickle"
    token_file.write_bytes(b"token")
    monkeypatch.setattr(remote_publish_module.config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        remote_publish_module.db,
        "get_channel",
        lambda channel_id: {
            "id": channel_id,
            "name": "Honjada",
            "credentials_path": "tokens/token_1.pickle",
            "proxy": None,
        },
    )
    release_calls = []
    monkeypatch.setattr(
        remote_publish_module.youtube_upload_service,
        "update_video_privacy",
        lambda *args, **kwargs: release_calls.append((args, kwargs)) or {},
    )
    updates = []
    monkeypatch.setattr(
        remote_publish_module.web_admin_client,
        "supabase_patch",
        lambda table, payload, *, params, timeout: updates.append((table, payload)) or FakeResponse([{"id": "publish-1", **payload}]),
    )
    monkeypatch.setattr(
        remote_publish_module.web_admin_client,
        "supabase_get",
        lambda *args, **kwargs: FakeResponse([]),
    )

    result = RemotePublishService("render-pc-1").process_claimed_request({
        "id": "publish-1",
        "status": "to_be_published",
        "metadata": {
            "project_id": 1000003340,
            "publish_operation": "release",
            "channel_id": 1,
            "videoId": "youtube-123",
        },
    })

    assert result["status"] == "public"
    assert release_calls == [(("youtube-123", "public"), {"token_path": str(token_file), "proxy": None})]
    assert updates[0][1]["status"] == "public"


def test_worker_process_polls_remote_publish_queue_and_render_completion_is_ready():
    root = Path(__file__).resolve().parents[1]
    process_source = (root / "worker" / "remote_drive_worker_process.py").read_text(encoding="utf-8")
    render_source = (root / "remote_drive_worker.py").read_text(encoding="utf-8")
    admin_source = (root / "auth-web" / "components" / "DashboardContent.tsx").read_text(encoding="utf-8")
    route_source = (root / "auth-web" / "app" / "api" / "admin" / "render-queue" / "route.ts").read_text(encoding="utf-8")

    assert "publisher.fetch_next_request()" in process_source
    assert "publisher.claim_request(publish_request)" in process_source
    assert '"admin_publish_status": "pending_review"' in render_source
    assert "completedRenderQueue" in admin_source
    assert "renderRenderQueueTable(completedRenderQueue)" in admin_source
    assert "publishInProgress" in admin_source
    assert "publishComplete" in admin_source
    assert "alreadyQueued: true" in route_source
    assert "['published', 'release_requested', 'public'].includes(existingStatus)" in route_source
