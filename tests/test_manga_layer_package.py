import base64
import hashlib
import json
import io
import pathlib
import sys
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from psd_tools import PSDImage

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "worker"))
import cowork_scene_assets as publisher
import manga_layer_package as layers


def _scene():
    return {
        "scene_number": 1,
        "ae_effect_plan": {
            "enabled": True,
            "template": "angled_triple_reaction",
            "asset_requirements": {
                "required_layers": ["background", "character_left", "character_center", "character_right"],
                "optional_layers": ["speedlines"],
            },
        },
    }


def _layer(path, *, background=False):
    image = Image.new("RGBA", layers.CANVAS_SIZE,
                      (30, 40, 50, 255) if background else (0, 0, 0, 0))
    if not background:
        ImageDraw.Draw(image).rectangle((250, 150, 700, 850), fill=(220, 90, 120, 255))
    image.save(path)


def _manifest(path):
    path.write_text(json.dumps({
        "schema": "cowork_scene_assets/v1", "topic_id": "topic-1", "bucket": "air-studio-prod",
        "scene_specs": [_scene()],
        "grids": [{"scene_numbers": [1]}],
    }), encoding="utf-8")


def test_missing_authored_layers_mark_needs_review_without_fake_psd(tmp_path):
    manifest = tmp_path / "manifest.json"
    _manifest(manifest)
    images = tmp_path / "images"
    images.mkdir()
    _layer(images / "scene-001.png", background=True)
    spec = layers.scene_specs([_scene()])

    with pytest.raises(ValueError, match="need review"):
        layers.prepare(manifest, images, spec)
    issue = json.loads(layers.issues_path(images).read_text(encoding="utf-8"))
    assert issue["issues"][0]["status"] == "needs_review"
    assert "background" in issue["issues"][0]["required_layers"]
    assert not (images / "layer-packages" / "scene-001.psd").exists()


def test_flattened_opaque_character_is_not_accepted_as_cutout(tmp_path):
    manifest = tmp_path / "manifest.json"
    _manifest(manifest)
    images = tmp_path / "images"
    images.mkdir()
    spec = layers.scene_specs([_scene()])[0]
    for role in spec["required_layers"]:
        _layer(images / spec["layer_files"][role], background=True)
    with pytest.raises(ValueError, match="need review"):
        layers.prepare(manifest, images, [spec])
    issues = json.loads(layers.issues_path(images).read_text(encoding="utf-8"))["issues"]
    assert "visible transparent cutout" in issues[0]["reason"]


def test_approved_real_psd_publishes_layer_metadata_and_detects_tamper(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    _manifest(manifest)
    images = tmp_path / "images"
    images.mkdir()
    _layer(images / "scene-001.png", background=True)
    spec = layers.scene_specs([_scene()])[0]
    for role in spec["required_layers"]:
        _layer(images / spec["layer_files"][role], background=role == "background")
    receipt = layers.prepare(manifest, images, [spec])
    psd_file = images / receipt["packages"]["1"]["psd_file"]
    reopened = PSDImage.open(psd_file)
    assert [layer.name for layer in reopened] == spec["required_layers"]
    assert reopened.size == layers.CANVAS_SIZE

    calls = []
    structure = {"scenes": [_scene()]}
    monkeypatch.setattr(publisher, "_topic", lambda *_: ({"id": "topic-1", "status": "assigned"}, structure, "https://db.test", {}))
    monkeypatch.setattr(publisher, "_upload_gcs_file", lambda path, object_path, mime: (
        calls.append((path, object_path, mime)) or ("air-studio-prod", object_path, "url:" + object_path)))
    patched = []
    def publish_rpc(method, url, headers, **kwargs):
        patched.append((method, url, kwargs["json"]))
        return SimpleNamespace(json=lambda: {"applied": True, "scenes_updated": 1})
    monkeypatch.setattr(publisher, "_request", publish_rpc)
    propagated = []
    monkeypatch.setattr(publisher, "_propagate_published_template_assets",
                        lambda topic, base, headers: propagated.append(topic))

    with pytest.raises(ValueError, match="needs visual review"):
        publisher.publish(manifest, images, False)
    assert calls == []

    layers.approve(manifest, images, [spec], reviewer="artist", note="Panels and alpha edges inspected")
    assert len(publisher.publish(manifest, images, False)) == 1
    assert propagated == ["topic-1"]
    assert any(path.suffix == ".psd" and mime == "image/vnd.adobe.photoshop" for path, _, mime in calls)
    scene_upload = next(object_path for path, object_path, _ in calls if path.name == "scene-001.png")
    assert scene_upload == f"topics/topic-1/images/scene-001-{publisher._file_sha256(images / 'scene-001.png')}.png"
    psd_upload = next(object_path for path, object_path, _ in calls if path.suffix == ".psd")
    assert psd_upload == f"topics/topic-1/layers/scene-001-{receipt['packages']['1']['psd_sha256']}.psd"
    assert patched[0][:2] == ("POST", "https://db.test/rest/v1/rpc/air_patch_topic_scene_assets")
    assert set(patched[0][2]) == {"p_topic_id", "p_scene_updates"}
    update = patched[0][2]["p_scene_updates"][0]
    assert update["expected_source"]["ae_effect_plan"] == _scene()["ae_effect_plan"]
    assert update["expected_assets"]["metadata"]["psd_layer_asset"] is None
    saved = update["asset_patch"]
    assert saved["metadata"]["psd_layer_asset"]["layers"] == spec["required_layers"]
    assert saved["metadata"]["psd_layer_asset"]["qa_status"] == "approved"
    assert saved["metadata"]["psd_layer_asset"]["gcs_path"] == psd_upload
    assert saved["psd_layer_status"] == "ready"

    calls.clear()
    scene_plan = structure["scenes"][0]["ae_effect_plan"]
    scene_plan["direction"] = "different impact timing"
    with pytest.raises(ValueError, match="art direction or timing changed"):
        publisher.publish(manifest, images, False)
    assert calls == []
    del scene_plan["direction"]

    changed = Image.new("RGBA", layers.CANVAS_SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(changed).ellipse((350, 150, 850, 850), fill=(40, 210, 160, 255))
    changed.save(images / spec["layer_files"]["character_left"])
    calls.clear()
    with pytest.raises(ValueError, match="changed after preparation"):
        publisher.publish(manifest, images, False)
    assert calls == []


def test_defer_layers_publishes_still_without_running_ae_asset_preparation(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    _manifest(manifest)
    images = tmp_path / "images"
    images.mkdir()
    _layer(images / "scene-001.png", background=True)

    scene = {**_scene(), "local_layer_plan": {"enabled": True}}
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["scene_specs"] = [scene]
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    structure = {"scenes": [scene]}
    monkeypatch.setattr(publisher, "_topic", lambda *_: (
        {"id": "topic-1", "status": "pending"}, structure, "https://db.test", {}))
    object_path = f"topics/topic-1/images/scene-001-{publisher._file_sha256(images / 'scene-001.png')}.png"
    expected_md5 = base64.b64encode(hashlib.md5((images / "scene-001.png").read_bytes()).digest()).decode("ascii")
    monkeypatch.setattr(publisher, "_list_gcs_object_metadata", lambda *_: {
        object_path: {"name": object_path, "size": str((images / "scene-001.png").stat().st_size),
                      "md5Hash": expected_md5}})
    monkeypatch.setattr(publisher, "_upload_gcs_file", lambda *args: pytest.fail(
        "verified immutable GCS image must not be uploaded again"))
    patched = []
    monkeypatch.setattr(publisher, "_request", lambda *args, **kwargs: (
        patched.append(kwargs["json"]) or SimpleNamespace(json=lambda: {"applied": True})))
    monkeypatch.setattr(publisher, "_write_depth_proxy_layers", lambda *args: pytest.fail(
        "deferred publishing must not prepare AE depth layers"))

    assert len(publisher.publish(manifest, images, False, defer_layers=True,
                                 reuse_existing=True)) == 1
    assert patched[0]["p_scene_updates"][0]["asset_patch"]["image_url"].startswith(
        "/api/std/assets/gcs-file?")
    assert "psd_layer_asset" not in patched[0]["p_scene_updates"][0]["asset_patch"]["metadata"]


def test_manifest_keeps_scene_bucket_distinct_from_portrait_bucket(tmp_path, monkeypatch):
    portrait = Image.new("RGB", (512, 512), (40, 50, 70))
    stream = io.BytesIO()
    portrait.save(stream, format="PNG")
    anchors = {"main_character": {"name": "장주", "character_key": "master",
                                  "image_url": "portrait-url", "gcs_bucket": "portrait-bucket",
                                  "gcs_path": "characters/master.png"}}
    structure = {"character_anchors": anchors,
                 "scenes": [{"scene_number": n, "image_prompt": f"scene {n}"} for n in range(1, 5)],
                 "image_grid_prompts": [{"scene_numbers": [1, 2, 3, 4], "prompt": "four scenes"}]}
    monkeypatch.setattr(publisher, "_topic", lambda *_: ({"id": "topic-1"}, structure, "", {}))
    seen = []
    monkeypatch.setattr(publisher, "_download_gcs_bytes", lambda bucket, path: (
        seen.append((bucket, path)) or stream.getvalue()))
    path = publisher.export_manifest("topic-1", tmp_path / "manifest.json", "scene-bucket")
    exported = json.loads(path.read_text(encoding="utf-8"))
    assert exported["bucket"] == "scene-bucket"
    assert seen == [("portrait-bucket", "characters/master.png")]


def test_candidate_plan_published_psd_is_accepted_by_ae_preflight(tmp_path, monkeypatch):
    import ae_highlight_worker as ae
    import codex_content_runner as content

    scene = {"scene_number": 1, "duration_seconds": 4,
             "scene_text": "장주가 부적을 맞는 순간 먹빛 충격이 터졌다.",
             "scene_summary": "부적이 장주를 타격한다",
             "image_prompt": "Korean wuxia manhwa, talisman impact",
             "ae_template": "ink_splat_impact", "ae_character_roles": {"character": "장주"}}
    anchors = {"main_character": {"name": "장주", "character_key": "master"},
               "supporting_characters": []}
    content._plan_ae_effects_for_scenes([scene], {"character_anchors": anchors, "category": "무협"})
    assert scene["ae_effect_plan"]["enabled"]
    assert scene["ae_effect_plan"]["character_role_keys"] == {"character": "master"}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema": "cowork_scene_assets/v1", "topic_id": "topic-2",
        "bucket": "scene-bucket", "scene_specs": [scene],
        "grids": [{"scene_numbers": [1]}]}, ensure_ascii=False), encoding="utf-8")
    images = tmp_path / "images"
    images.mkdir()
    _layer(images / "scene-001.png", background=True)
    spec = layers.scene_specs([scene])[0]
    for role in spec["required_layers"]:
        _layer(images / spec["layer_files"][role], background=role == "background")
    receipt = layers.prepare(manifest, images, [spec])
    layers.approve(manifest, images, [spec], reviewer="artist", note="Character, talisman, and alpha reviewed")

    structure = {"scenes": [scene]}
    monkeypatch.setattr(publisher, "_topic", lambda *_: ({"id": "topic-2"}, structure, "https://db.test", {}))
    monkeypatch.setattr(publisher, "_upload_gcs_file", lambda path, object_path, mime: (
        "scene-bucket", object_path, "url:" + object_path))
    monkeypatch.setattr(publisher, "_request", lambda *args, **kwargs:
                        SimpleNamespace(json=lambda: {"applied": True, "scenes_updated": 1}))
    monkeypatch.setattr(publisher, "_propagate_published_template_assets", lambda *args: {"applied": True})
    publisher.publish(manifest, images, False)

    source = ae._gcs_ref_from_scene(scene)
    assert source and source.bucket == "scene-bucket"
    assert source.path == scene["metadata"]["psd_layer_asset"]["gcs_path"]
    assert source.path.endswith(receipt["packages"]["1"]["psd_sha256"] + ".psd")
    psd_path = images / receipt["packages"]["1"]["psd_file"]
    report = ae._manga_preflight(SimpleNamespace(scene=scene, duration_seconds=4), psd_path)
    assert report["passed"]
    assert "talisman" in report["layer_centers"]
    scene["metadata"]["psd_layer_asset"]["sha256"] = "0" * 64
    with pytest.raises(ae.AeReviewRequired, match="differs from the approved"):
        ae._manga_preflight(SimpleNamespace(scene=scene, duration_seconds=4), psd_path)


def test_project_sync_calls_atomic_rpc_for_submitted_and_unsubmitted_projects(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def request(method, url, headers, **kwargs):
        calls.append((method, url, kwargs))
        return Response({"applied": True, "projects_updated": 2,
                         "scenes_updated": 2, "requeued": 1})

    monkeypatch.setattr(publisher, "_request", request)
    result = publisher._propagate_published_template_assets("3197", "https://db.test", {})
    assert result["scenes_updated"] == 2
    assert calls == [("POST", "https://db.test/rest/v1/rpc/air_sync_manga_layer_assets",
                      {"json": {"p_topic_id": "3197"}})]
    monkeypatch.setattr(publisher, "_request", lambda *a, **k: Response({"applied": False, "code": "invalid_topic_id"}))
    with pytest.raises(RuntimeError, match="invalid_topic_id"):
        publisher._propagate_published_template_assets("bad", "https://db.test", {})


def test_topic_asset_patch_sends_owned_fields_only_and_rejects_db_conflict(monkeypatch):
    scene = {"scene_number": 2, "image_url": "new-url", "asset_status": "ready",
             "metadata": {"ae_effect_asset": {"status": "review_pending", "render_sha256": "a" * 64},
                          "cowork_image_asset": {"source": "cowork_builtin_imagegen"},
                          "psd_layer_asset": {"qa_status": "approved"}},
             "psd_layer_status": "ready", "ae_effect_status": "review_pending"}
    patch = publisher._scene_asset_patch(scene)
    assert set(patch) == {"image_url", "asset_status", "psd_layer_status", "metadata"}
    assert set(patch["metadata"]) == {"cowork_image_asset", "psd_layer_asset"}
    assert "ae_effect_asset" not in patch["metadata"]
    assert "ae_effect_status" not in patch

    calls = []
    def request(method, url, headers, **kwargs):
        calls.append((method, url, kwargs["json"]))
        return SimpleNamespace(json=lambda: {"applied": False, "code": "asset_conflict",
                                             "scene_number": "2"})
    monkeypatch.setattr(publisher, "_request", request)
    updates = [{"scene_number": 2, "expected_source": {}, "expected_assets": {},
                "asset_patch": patch}]
    with pytest.raises(RuntimeError, match="asset_conflict"):
        publisher._patch_topic_scene_assets("3197", updates, "https://db.test", {})
    assert calls == [("POST", "https://db.test/rest/v1/rpc/air_patch_topic_scene_assets",
                      {"p_topic_id": "3197", "p_scene_updates": updates})]


def test_topic_asset_patch_migration_is_row_locked_atomic_and_service_only():
    migration = pathlib.Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20260926134000_atomic_topic_scene_asset_publish.sql"
    sql = migration.read_text(encoding="utf-8")
    assert "from public.topics_queue where id::text = p_topic_id for update" in sql
    assert "v_source is distinct from v_item -> 'expected_source'" in sql
    assert "v_current_assets is distinct from v_item -> 'expected_assets'" in sql
    assert "v_next_scene := v_scene || (v_patch - 'metadata')" in sql
    assert "v_meta || v_patch_meta" in sql
    assert sql.index("update public.topics_queue set pregenerated_structure") > sql.index("end loop;")
    assert "current_user <> 'service_role'" in sql
    assert "grant execute on function public.air_patch_topic_scene_assets(text, jsonb)" in sql


def test_project_sync_migration_locks_rows_and_limits_missing_psd_requeue():
    migration = pathlib.Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20260926132500_sync_manga_layer_assets.sql"
    sql = migration.read_text(encoding="utf-8")
    assert "from public.topics_queue where id::text = p_topic_id for update" in sql
    assert "order by id for update" in sql
    assert "'review_requested'" in sql  # A submitted project may receive the PSD before AE starts.
    assert "v_claim_scene -> 'ae_effect_plan'" in sql
    assert "v_project_scene -> 'ae_effect_plan'" in sql
    assert "Visual review rejected" not in sql  # Human rejection is not an automatic retry reason.
    assert "v_error like 'Manga template needs a layered PSD%'" in sql
    assert "v_error like 'Manga PSD layer package has not passed layer review%'" in sql
    assert "status', 'planned'" in sql
