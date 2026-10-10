from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))


def test_manga_template_registries_agree_across_planning_assets_qa_and_ae():
    from codex_content_runner import AE_MANGA_TEMPLATES
    from manga_ae_templates import MANGA_TEMPLATES
    from manga_layer_package import TEMPLATE_REQUIRED, TEMPLATE_OPTIONAL
    from manga_scene_qa import TEMPLATES

    assert (set(AE_MANGA_TEMPLATES) == set(MANGA_TEMPLATES)
            == set(TEMPLATE_REQUIRED) == set(TEMPLATE_OPTIONAL) == set(TEMPLATES))
    for template, spec in AE_MANGA_TEMPLATES.items():
        assert set(spec["required_layers"]) == set(TEMPLATE_REQUIRED[template]) == set(TEMPLATES[template])
        assert set(spec["optional_layers"]) <= set(TEMPLATE_OPTIONAL[template])


def _pending_scene(mp4: Path) -> dict:
    digest = hashlib.sha256(mp4.read_bytes()).hexdigest()
    return {
        "scene_number": 1,
        "ae_effect_plan": {"enabled": True, "template": "body_following_qi"},
        "metadata": {"ae_effect_asset": {
            "status": "review_pending", "storage_provider": "local",
            "local_path": str(mp4), "review_local_path": str(mp4),
            "local_bytes": mp4.stat().st_size, "render_sha256": digest,
            "manga_qa": {"plan": {"passed": True}, "render": {"passed": True}},
        }},
    }


def test_review_approval_is_bound_to_video_hash_and_unblocks_premiere(tmp_path, monkeypatch):
    import manga_scene_review as review
    import premiere_final_worker as premiere

    root = tmp_path / "ae_highlight"
    root.mkdir()
    clip = root / "scene.mp4"
    clip.write_bytes(b"valid-video" * 500)
    scene = _pending_scene(clip)
    structure = {"scenes": [scene]}
    row = {"id": "project", "title": "wuxia", "submitted_at": "2026-09-26T00:00:00Z",
           "project_payload": {"structure": structure}, "progress_payload": {}}
    monkeypatch.setattr(premiere, "_local_ref_from_asset", lambda asset: Path(asset["local_path"]))
    monkeypatch.setattr(premiere, "_scene_media_ref", lambda item: ("local", clip))
    assert premiere.find_project_jobs([row]) == []

    expected_hash = scene["metadata"]["ae_effect_asset"]["render_sha256"]
    with pytest.raises(ValueError, match="hash changed"):
        review.apply_review(structure, scene_number=1, decision="approved", reviewer="tester",
                            note="faces and timing checked", expected_sha256="0" * 64,
                            allowed_media_root=root)
    review.apply_review(structure, scene_number=1, decision="approved", reviewer="tester",
                        note="faces and timing checked", expected_sha256=expected_hash,
                        allowed_media_root=root)
    assert scene["metadata"]["ae_effect_asset"]["status"] == "ready"
    assert premiere.find_project_jobs([row])


def test_review_rejection_keeps_scene_out_of_final_output(tmp_path, monkeypatch):
    import manga_scene_review as review
    import premiere_final_worker as premiere

    root = tmp_path / "ae_highlight"
    root.mkdir()
    clip = root / "scene.mp4"
    clip.write_bytes(b"video" * 500)
    scene = _pending_scene(clip)
    structure = {"scenes": [scene]}
    review.apply_review(structure, scene_number=1, decision="rejected", reviewer="tester",
                        note="text is unreadable", expected_sha256=scene["metadata"]["ae_effect_asset"]["render_sha256"],
                        allowed_media_root=root)
    assert scene["ae_effect_status"] == "needs_attention"
    monkeypatch.setattr(premiere, "_local_ref_from_asset", lambda asset: Path(asset["local_path"]))
    row = {"id": "project", "title": "wuxia", "submitted_at": "2026-09-26T00:00:00Z",
           "project_payload": {"structure": structure}, "progress_payload": {}}
    assert premiere.find_project_jobs([row]) == []


def test_user_uploaded_clip_is_blocked_from_final_render_until_ae_ready(monkeypatch):
    import premiere_final_worker as premiere

    scene = {
        "scene_number": 1,
        "video_generation_mode": "user_upload",
        "video_url": "/api/std/assets/gcs-file?bucket=b&path=source.mp4",
        "ae_motion_plan": {"enabled": True},
    }
    row = {"id": "project", "submitted_at": "2026-09-26T00:00:00Z",
           "project_payload": {"structure": {"scenes": [scene]}}}
    assert premiere.find_project_jobs([row]) == []

    scene["ae_motion_video_url"] = "/api/std/assets/gcs-file?bucket=b&path=ae.mp4"
    assert premiere.find_project_jobs([row])


def test_manga_jsx_uses_structured_impact_time_and_text(tmp_path):
    from manga_ae_templates import write_manga_jsx

    scene = {"ae_effect_plan": {"enabled": True, "template": "ink_splat_impact",
                                "impact": {"x": .51, "y": .56, "at_seconds": .8, "text": "펑!"},
                                "beats": [{"at_seconds": .8, "action": "impact_flash"}]}}
    jsx = tmp_path / "scene.jsx"
    write_manga_jsx(scene=scene, input_psd=tmp_path / "scene.psd",
                    project_path=tmp_path / "scene.aep", render_path=tmp_path / "scene.mp4",
                    jsx_path=jsx, comp_name="ae_highlight_comic_ink_splat_impact",
                    width=1920, height=1080, fps=24, duration=4)
    script = jsx.read_text(encoding="utf-8")
    assert "ImportAsType.COMP" in script and "impact_onomatopoeia" in script
    assert '"at_seconds": 0.8' in script and "\\uD384" not in script
    assert 'firstBeat("ink_splat", moment + 0.06)' in script
    assert 'firstBeat("onomatopoeia", moment + 0.12)' in script
    assert 'layer.inPoint = at(when)' in script
    assert 'success.write("success|" + CFG.project' in script
    assert 'app.scheduleTask("app.quit()"' in script
    assert 'throw error;' in script
    assert "__MANGA_CONFIG__" not in script


def test_parallax_jsx_combines_reviewed_layers_with_eye_and_mouth_runtime(tmp_path):
    from manga_ae_templates import write_manga_jsx

    scene = {"ae_effect_plan": {"enabled": True, "template": "parallax_layered_scene",
        "layer_animation": {"camera": {"zoom": .025}, "hair_cloth": {"sway_degrees": .55}}},
        "ae_mouth_runtime": {"enabled": True, "speakers": [], "blinks": []}}
    jsx = tmp_path / "layered.jsx"
    write_manga_jsx(scene=scene, input_psd=tmp_path / "scene.psd",
                    project_path=tmp_path / "scene.aep", render_path=tmp_path / "scene.mp4",
                    jsx_path=jsx, comp_name="layered", width=1920, height=1080, fps=24, duration=5)
    script = jsx.read_text(encoding="utf-8")
    assert 'layerByRole(comp, "character", true)' in script
    assert 'layerByRole(comp, "hair_cloth", false)' in script
    assert 'layerByRole(comp, "light_overlay", false)' in script
    assert "addRuntimePatches(comp, character)" in script
    assert '"runtime": {"enabled": true' in script
