"""Prepare, crop, and publish CoWork-generated storyboard image grids.

This script deliberately does not call an image-generation API.  A CoWork
agent uses the built-in image tool for each exported grid prompt, then this
script crops the returned grids and persists the scene mapping in Supabase.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import mimetypes
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFilter
from PIL import ImageOps
try:
    from . import image_recovery
    from . import manga_layer_generation
    from . import manga_layer_package
except ImportError:
    import image_recovery
    import manga_layer_generation
    import manga_layer_package


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUCKET = os.getenv("GCS_BUCKET_NAME") or "air-studio-prod"
DEFAULT_ASSET_WIDTH = 1920
DEFAULT_ASSET_HEIGHT = 1080


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("pregenerated_structure is not a JSON object")


def _supabase() -> tuple[str, dict[str, str]]:
    load_dotenv(ROOT / ".env", override=True)
    url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def _request(method: str, url: str, headers: dict[str, str], **kwargs: Any) -> requests.Response:
    response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    if not response.ok:
        raise RuntimeError(f"Supabase request failed ({response.status_code}): {response.text[:500]}")
    return response


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gcs_credentials():
    client_email = os.getenv("GCS_CLIENT_EMAIL") or os.getenv("GOOGLE_CLIENT_EMAIL") or ""
    private_key = os.getenv("GCS_PRIVATE_KEY") or os.getenv("GOOGLE_PRIVATE_KEY") or ""
    project_id = os.getenv("GCS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "air-studio-prod"
    bucket = os.getenv("GCS_BUCKET_NAME") or DEFAULT_BUCKET
    if not (client_email and private_key and bucket):
        raise RuntimeError("GCS credentials are required for scene image publishing")
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    creds = service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "project_id": project_id,
            "private_key": private_key.replace("\\n", "\n"),
            "client_email": client_email,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
    )
    creds.refresh(Request())
    return creds, bucket


def _upload_gcs_file(file_path: Path, object_path: str, mime_type: str) -> tuple[str, str, str]:
    creds, bucket = _gcs_credentials()
    clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_path:
        raise RuntimeError("GCS object path is empty")
    with file_path.open("rb") as handle:
        response = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
            f"?uploadType=media&name={quote(clean_path, safe='')}",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": mime_type},
            data=handle,
            timeout=300,
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"GCS scene image upload failed ({response.status_code}): {response.text[:300]}")
    return bucket, clean_path, f"/api/std/assets/gcs-file?bucket={quote(bucket, safe='')}&path={quote(clean_path, safe='')}"


def _download_gcs_bytes(bucket: str, object_path: str) -> bytes:
    creds, default_bucket = _gcs_credentials()
    target_bucket = bucket or default_bucket
    clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_path:
        raise RuntimeError("GCS object path is empty")
    response = requests.get(
        f"https://storage.googleapis.com/storage/v1/b/{quote(target_bucket, safe='')}/o/"
        f"{quote(clean_path, safe='')}?alt=media",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=300,
    )
    if response.status_code != 200:
        raise RuntimeError(f"GCS character reference download failed ({response.status_code}): {response.text[:300]}")
    return response.content


def _topic(topic_id: str) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, str]]:
    base_url, headers = _supabase()
    safe_id = quote(topic_id, safe="")
    response = _request(
        "GET",
        f"{base_url}/rest/v1/topics_queue?id=eq.{safe_id}&select=id,topic,generated_title,status,pregenerated_structure,pregenerated_structure_status",
        headers,
    )
    rows = response.json()
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"topics_queue row not found for id={topic_id}")
    row = rows[0]
    return row, _json(row.get("pregenerated_structure")), base_url, headers


def _scene_number(scene: dict[str, Any], fallback: int) -> int:
    value = scene.get("scene_number") or scene.get("scene_order") or fallback
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid scene number: {value!r}") from exc
    if number < 1:
        raise ValueError(f"invalid scene number: {number}")
    return number


def _template_source_snapshot(scene: dict[str, Any], fallback: int) -> dict[str, Any]:
    """Art direction and timed beats that the approved PSD must still match."""
    return {
        "scene_number": _scene_number(scene, fallback),
        "scene_text": scene.get("scene_text") or scene.get("narration"),
        "image_prompt": scene.get("image_prompt"),
        "image_style": scene.get("image_style"),
        "ae_effect_plan": scene.get("ae_effect_plan") if isinstance(scene.get("ae_effect_plan"), dict) else {},
    }


_PUBLISHED_METADATA_KEYS = (
    "cowork_image_asset", "local_layer_plan", "local_layer_asset",
    "psd_layer_asset", "psd_layer_plan",
)


def _publish_source_snapshot(scene: dict[str, Any], fallback: int) -> dict[str, Any]:
    """Fields that bind uploaded art to the current scene under the DB row lock."""
    snapshot = _template_source_snapshot(scene, fallback)
    for key in ("image_generation_policy", "local_layer_plan", "psd_layer_plan"):
        value = scene.get(key)
        snapshot[key] = copy.deepcopy(value) if isinstance(value, dict) else {}
    return snapshot


def _scene_asset_snapshot(scene: dict[str, Any]) -> dict[str, Any]:
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    return {
        "image_url": copy.deepcopy(scene.get("image_url")),
        "asset_status": copy.deepcopy(scene.get("asset_status")),
        "local_layer_status": copy.deepcopy(scene.get("local_layer_status")),
        "psd_layer_status": copy.deepcopy(scene.get("psd_layer_status")),
        "metadata": {key: copy.deepcopy(metadata.get(key)) for key in _PUBLISHED_METADATA_KEYS},
    }


def _scene_asset_patch(scene: dict[str, Any]) -> dict[str, Any]:
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    patch = {
        "image_url": scene["image_url"],
        "asset_status": "ready",
        "metadata": {key: copy.deepcopy(metadata[key]) for key in _PUBLISHED_METADATA_KEYS if key in metadata},
    }
    for key in ("local_layer_status", "psd_layer_status"):
        if key in scene:
            patch[key] = scene[key]
    return patch


def _patch_topic_scene_assets(topic_id: str, updates: list[dict[str, Any]],
                              base_url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Atomically merge scene assets without replacing concurrent AE state."""
    result = _request(
        "POST", f"{base_url}/rest/v1/rpc/air_patch_topic_scene_assets",
        {**headers, "Content-Type": "application/json"},
        json={"p_topic_id": str(topic_id), "p_scene_updates": updates},
    ).json()
    if not isinstance(result, dict) or result.get("applied") is not True:
        raise RuntimeError(f"Atomic topic scene asset publish failed: {result}")
    return result


def export_manifest(topic_id: str, destination: Path, bucket: str) -> Path:
    if destination.exists():
        raise FileExistsError('Preserve existing manifest/recovery state; use a new revision path')
    row, structure, _base_url, _ = _topic(topic_id)
    scenes = structure.get("scenes")
    grids = structure.get("image_grid_prompts")
    if not isinstance(scenes, list) or not scenes:
        raise RuntimeError("topic has no scenes")
    if not isinstance(grids, list) or not grids:
        raise RuntimeError("topic has no image_grid_prompts")

    anchors = structure.get("character_anchors") or {}
    characters = [anchors.get("main_character") or structure.get("main_character")] + list(
        anchors.get("supporting_characters") or structure.get("supporting_characters") or [])
    if not characters[0] or any(not isinstance(c, dict) or not c.get("image_url") for c in characters):
        raise RuntimeError("Generate and publish principal character reference images before scene images")
    destination.parent.mkdir(parents=True, exist_ok=True)
    references = []
    for index, character in enumerate(characters, 1):
        url = str(character["image_url"] or "")
        metadata = character.get("metadata") if isinstance(character.get("metadata"), dict) else {}
        character_bucket = str(character.get("gcs_bucket") or character.get("storage_bucket") or metadata.get("gcs_bucket") or "").strip()
        object_path = str(character.get("gcs_path") or character.get("storage_object_path") or metadata.get("gcs_path") or "").strip()
        if not object_path:
            raise RuntimeError("Character reference must include a GCS object path")
        reference_path = destination.parent / f"character-reference-{index}.png"
        reference_path.write_bytes(_download_gcs_bytes(character_bucket, object_path))
        from codex_character_assets import validate_portrait
        validate_portrait(reference_path)
        references.append({"name": character.get("name"), "character_key": character.get("character_key"),
                           "image_url": url, "local_file": str(reference_path.resolve()),
                           "sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest()})

    known_scenes = {_scene_number(scene, index) for index, scene in enumerate(scenes, start=1) if isinstance(scene, dict)}
    manifest_grids: list[dict[str, Any]] = []
    covered: set[int] = set()
    for index, grid in enumerate(grids, start=1):
        if not isinstance(grid, dict):
            raise ValueError(f"grid {index} is invalid")
        numbers = grid.get("scene_numbers")
        prompt = str(grid.get("prompt") or "").strip()
        if not isinstance(numbers, list) or len(numbers) != 4 or not prompt:
            raise ValueError(f"grid {index} must have four scenes and a prompt")
        scene_numbers = [int(number) for number in numbers]
        if any(number not in known_scenes for number in scene_numbers):
            raise ValueError(f"grid {index} references an unknown scene")
        covered.update(scene_numbers)
        grid_number = int(grid.get("grid_number") or index)
        manifest_grids.append(
            {
                "grid_number": grid_number,
                "scene_numbers": scene_numbers,
                "prompt": prompt,
                "raw_file": f"grid-{grid_number:03d}.png",
                "character_references": references,
            }
        )
    missing = sorted(known_scenes - covered)
    if missing:
        raise ValueError(f"image grids do not cover scene(s): {missing}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "cowork_scene_assets/v1",
        "topic_id": str(row["id"]),
        "title": str(row.get("generated_title") or row.get("topic") or ""),
        "bucket": bucket,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scene_count": len(known_scenes),
        "character_references": references,
        "scene_specs": [{"scene_number": _scene_number(s, i), "scene_id": s.get("scene_id"),
                         "scene_text": s.get("scene_text") or s.get("narration"),
                         "image_prompt": s.get("image_prompt"), "image_style": s.get("image_style"),
                         "ae_effect_plan": s.get("ae_effect_plan") if isinstance(s.get("ae_effect_plan"), dict) else {},
                         "image_generation_policy": s.get("image_generation_policy") if isinstance(s.get("image_generation_policy"), dict) else {},
                         "local_layer_plan": s.get("local_layer_plan") if isinstance(s.get("local_layer_plan"), dict) else {},
                         "psd_layer_plan": s.get("psd_layer_plan") if isinstance(s.get("psd_layer_plan"), dict) else {}}
                        for i, s in enumerate(scenes, 1)],
        "image_layer_mode": structure.get("image_layer_mode") or (structure.get("image_generation_policy") or {}).get("image_layer_mode") or "hybrid",
        "psd_layer_prompt_status": structure.get("psd_layer_prompt_status") or "not_required",
        "psd_layer_prompts": structure.get("psd_layer_prompts") if isinstance(structure.get("psd_layer_prompts"), list) else [],
        "layer_package_specs": manga_layer_package.scene_specs(scenes),
        "layer_package_instruction": "For every required layer_package_specs role, supply an independently authored full-canvas 1920x1080 PNG named exactly as layer_files. All foreground roles, including characters, hand, intact/broken wall, reflection plate and props, need visible transparent alpha; background must cover the canvas. The broken wall must preserve the intact wall's geometry, and the hand must use a verified character reference. A flattened scene crop or soft depth proxy is not a separate role layer. Run generate-layers or supply role PNGs, then prepare-layers, inspect each PSD preview, and approve-layers before publish.",
        "recovery_policy": image_recovery.POLICY,
        "recovery_instruction": "Before every native tool call, start its recovery job; record its result and visual review. Safety/unknown failures must not be automatically retried or split. See docs/IMAGE_GENERATION_RECOVERY.md.",
        "generation_instruction": "Attach the character_references local PNGs as reference images to EVERY grid generation. Preserve each named character's face, age and wardrobe. Generate still images only, never video clips.",
        "grids": manifest_grids,
    }
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    image_recovery.ensure_state(destination)
    return destination


def _manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "cowork_scene_assets/v1":
        raise ValueError("not a CoWork scene-assets manifest")
    if not isinstance(data.get("grids"), list) or not data.get("topic_id"):
        raise ValueError("manifest is incomplete")
    return data


def _propagate_published_template_assets(topic_id: str, base_url: str,
                                         headers: dict[str, str]) -> dict[str, Any]:
    """Merge approved assets under project row locks, including submitted work.

    The database RPC compares each scene with its claim-time source and leaves
    in-progress AE, user-edited scenes, and human-rejected renders untouched.
    """
    result = _request(
        "POST", f"{base_url}/rest/v1/rpc/air_sync_manga_layer_assets",
        {**headers, "Content-Type": "application/json"},
        json={"p_topic_id": str(topic_id)},
    ).json()
    if not isinstance(result, dict) or result.get("applied") is not True:
        raise RuntimeError(f"Manga layer project sync failed: {result}")
    return result


def _crop_to_aspect(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Center-crop a panel only when the supplied grid is not 16:9 accurate."""
    target_ratio = target_width / target_height
    width, height = image.size
    source_ratio = width / height
    if source_ratio > target_ratio:
        cropped_width = round(height * target_ratio)
        left = (width - cropped_width) // 2
        return image.crop((left, 0, left + cropped_width, height))
    if source_ratio < target_ratio:
        cropped_height = round(width / target_ratio)
        top = (height - cropped_height) // 2
        return image.crop((0, top, width, top + cropped_height))
    return image


def _upscale_panel(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Produce a delivery-sized still without relying on an image-generation API."""
    prepared = _crop_to_aspect(image, target_width, target_height)
    resized = prepared.resize((target_width, target_height), Image.Resampling.LANCZOS)
    return resized.filter(ImageFilter.UnsharpMask(radius=1.2, percent=105, threshold=3))


def _first_target(policy: dict[str, Any]) -> tuple[float, float]:
    targets = policy.get("targets") if isinstance(policy.get("targets"), list) else []
    for target in targets:
        if isinstance(target, dict):
            try:
                return max(0.05, min(float(target.get("x") or 0.5), 0.95)), max(0.05, min(float(target.get("y") or 0.52), 0.95))
            except (TypeError, ValueError):
                pass
    return 0.5, 0.52


def _write_depth_proxy_layers(source_path: Path, output_dir: Path, scene_number: int, policy: dict[str, Any]) -> dict[str, Path]:
    """Create no-credit proxy layers for subtle AE parallax from a single generated still."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    width, height = image.size
    cx_ratio, cy_ratio = _first_target(policy)
    cx, cy = int(width * cx_ratio), int(height * cy_ratio)
    rx, ry = int(width * 0.24), int(height * 0.36)
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(18, width // 48)))
    foreground = image.copy()
    foreground.putalpha(mask)
    background = image.convert("RGB").filter(ImageFilter.GaussianBlur(radius=8))
    foreground_path = output_dir / f"scene-{scene_number:03d}-foreground.png"
    background_path = output_dir / f"scene-{scene_number:03d}-background.png"
    foreground.save(foreground_path, format="PNG", optimize=True)
    background.save(background_path, format="PNG", optimize=True)
    return {"foreground_rgba": foreground_path, "background_plate": background_path}


def crop_grids(
    manifest_path: Path,
    input_dir: Path,
    output_dir: Path,
    *,
    target_width: int = DEFAULT_ASSET_WIDTH,
    target_height: int = DEFAULT_ASSET_HEIGHT,
) -> list[Path]:
    if target_width < 320 or target_height < 180:
        raise ValueError("output dimensions are too small for scene assets")
    manifest = _manifest(manifest_path)
    recovery_path = image_recovery.state_path(manifest_path)
    jobs = None
    if manifest.get('recovery_policy') and not recovery_path.exists():
        raise ValueError('Recovery state missing; cannot bypass image review')
    if recovery_path.exists():
        jobs = image_recovery.recipes(json.loads(recovery_path.read_text(encoding='utf-8')), manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    assigned: set[int] = set()
    for grid in jobs if jobs is not None else manifest["grids"]:
        raw_path = Path(grid['image_file']) if jobs is not None else input_dir / str(grid["raw_file"])
        if not raw_path.is_file():
            raise FileNotFoundError(f"generated grid is missing: {raw_path}")
        scene_numbers = grid.get("scene_numbers")
        single = grid.get('layout') == 'single'
        if not isinstance(scene_numbers, list) or len(scene_numbers) != (1 if single else 4):
            raise ValueError(f"grid {grid.get('grid_number')} does not map exactly four scenes")
        with Image.open(raw_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            width, height = image.size
            if width < 4 or height < 4:
                raise ValueError(f"grid {raw_path.name} is too small to crop")
            x_mid, y_mid = width // 2, height // 2
            boxes = ((0, 0, width, height),) if single else ((0, 0, x_mid, y_mid), (x_mid, 0, width, y_mid), (0, y_mid, x_mid, height), (x_mid, y_mid, width, height))
            for scene_number, box in zip(scene_numbers, boxes):
                number = int(scene_number)
                if number in assigned:
                    # Some 15-minute prepared topics use an overlapping final
                    # 2x2 grid (for example 49-52 followed by 50-53) so the
                    # last non-multiple-of-four scene can still be generated
                    # from a full four-panel source image. Keep the first
                    # already-cropped asset stable and only add scenes that do
                    # not exist yet.
                    continue
                assigned.add(number)
                target = output_dir / f"scene-{number:03d}.png"
                expected_image = _upscale_panel(image.crop(box), target_width, target_height)
                if target.exists():
                    with Image.open(target) as existing:
                        if existing.size != expected_image.size or existing.convert('RGB').tobytes() != expected_image.tobytes():
                            raise FileExistsError(f"refusing to overwrite different crop: {target}")
                    continue
                expected_image.save(
                    target, format="PNG", optimize=True
                )
                written.append(target)
    if jobs is not None:
        receipt = {"source_hash": image_recovery.digest(manifest), "files": {
            f"scene-{n:03d}.png": hashlib.sha256((output_dir / f"scene-{n:03d}.png").read_bytes()).hexdigest()
            for n in assigned}}
        (output_dir / 'crop-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return written


def publish(manifest_path: Path, images_dir: Path, create_bucket: bool) -> list[str]:
    manifest = _manifest(manifest_path)
    recovery_path = image_recovery.state_path(manifest_path)
    if manifest.get('recovery_policy') and not recovery_path.exists():
        raise ValueError('Recovery state missing; cannot publish')
    if recovery_path.exists():
        image_recovery.recipes(json.loads(recovery_path.read_text(encoding='utf-8')), manifest)
        receipt = json.loads((images_dir / 'crop-receipt.json').read_text(encoding='utf-8'))
        expected = {f"scene-{int(n):03d}.png" for g in manifest['grids'] for n in g['scene_numbers']}
        if receipt['source_hash'] != image_recovery.digest(manifest) or set(receipt['files']) != expected:
            raise ValueError('Crop receipt does not match manifest')
        for name, sha in receipt['files'].items():
            if hashlib.sha256((images_dir / name).read_bytes()).hexdigest() != sha:
                raise ValueError('Crop changed after review: ' + name)
    topic_id = str(manifest["topic_id"])
    bucket = str(manifest.get("bucket") or DEFAULT_BUCKET)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
        raise ValueError("bucket must be a safe lowercase storage bucket name")
    row, structure, base_url, headers = _topic(topic_id)
    manifest_layer_specs = manga_layer_package.scene_specs(manifest.get("scene_specs") or [])
    current_layer_specs = manga_layer_package.scene_specs(structure.get("scenes") or [])
    if manifest_layer_specs != current_layer_specs:
        raise ValueError("manga layer plan changed after manifest export; create a new manifest revision")
    manifest_sources = {
        source["scene_number"]: source
        for index, scene in enumerate(manifest.get("scene_specs") or [], 1)
        if isinstance(scene, dict)
        for source in [_publish_source_snapshot(scene, index)]
    }
    current_sources = {
        source["scene_number"]: source
        for index, scene in enumerate(structure.get("scenes") or [], 1)
        if isinstance(scene, dict)
        for source in [_publish_source_snapshot(scene, index)]
    }
    if manifest_sources != current_sources:
        raise ValueError("manga scene art direction or timing changed after manifest export; create a new revision")
    expected_assets = {
        _scene_number(scene, index): _scene_asset_snapshot(scene)
        for index, scene in enumerate(structure.get("scenes") or [], 1)
        if isinstance(scene, dict)
    }
    if manifest_layer_specs:
        selected = {spec["scene_number"] for spec in manifest_layer_specs}
        exported_sources = {
            snapshot["scene_number"]: snapshot
            for index, scene in enumerate(manifest.get("scene_specs") or [], 1)
            if isinstance(scene, dict)
            for snapshot in [_template_source_snapshot(scene, index)]
            if snapshot["scene_number"] in selected
        }
        current_sources = {
            snapshot["scene_number"]: snapshot
            for index, scene in enumerate(structure.get("scenes") or [], 1)
            if isinstance(scene, dict)
            for snapshot in [_template_source_snapshot(scene, index)]
            if snapshot["scene_number"] in selected
        }
        if exported_sources != current_sources:
            raise ValueError("manga scene art direction or timing changed after manifest export; create a new revision")
    layer_receipt = (manga_layer_package.validate_receipt(
        manifest_path, images_dir, manifest_layer_specs, require_approved=True)
        if manifest_layer_specs else None)
    if create_bucket:
        print("--create-bucket is ignored: scene images are uploaded to GCS, not Supabase Storage.", file=sys.stderr)

    scene_urls: dict[int, str] = {}
    scene_refs: dict[int, tuple[str, str]] = {}
    scene_layer_assets: dict[int, dict[str, Any]] = {}
    scene_psd_assets: dict[int, dict[str, Any]] = {}
    layer_dir = images_dir / "derived-layers"
    for grid in manifest["grids"]:
        for scene_number in grid["scene_numbers"]:
            number = int(scene_number)
            file_path = images_dir / f"scene-{number:03d}.png"
            if not file_path.is_file():
                raise FileNotFoundError(f"cropped scene file is missing: {file_path}")
            with Image.open(file_path) as asset_image:
                if asset_image.size != (DEFAULT_ASSET_WIDTH, DEFAULT_ASSET_HEIGHT):
                    raise ValueError(
                        f"scene {number} is not the required upscaled "
                        f"{DEFAULT_ASSET_WIDTH}x{DEFAULT_ASSET_HEIGHT} asset: {file_path}"
                    )
            # Immutable names keep a losing concurrent publisher from changing
            # the bytes behind the winning topic scene URL after the DB CAS.
            object_path = f"topics/{topic_id}/images/scene-{number:03d}-{_file_sha256(file_path)}.png"
            mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
            gcs_bucket, gcs_path, media_url = _upload_gcs_file(file_path, object_path, mime_type)
            scene_urls[number] = media_url
            scene_refs[number] = (gcs_bucket, gcs_path)
            if layer_receipt is not None and str(number) in layer_receipt["packages"]:
                package = layer_receipt["packages"][str(number)]
                psd_file = images_dir / package["psd_file"]
                # AE checkpoints identify their source by GCS object path. A
                # content-addressed PSD path prevents a later approved revision
                # from silently reusing an older local PSD or MP4.
                psd_object = f"topics/{topic_id}/layers/scene-{number:03d}-{package['psd_sha256']}.psd"
                pbucket, ppath, purl = _upload_gcs_file(psd_file, psd_object, "image/vnd.adobe.photoshop")
                scene_psd_assets[number] = {
                    "source": "independently_authored_png_layers",
                    "storage_provider": "gcs",
                    "gcs_bucket": pbucket,
                    "gcs_path": ppath,
                    "media_url": purl,
                    "template": package["template"],
                    "layers": [layer["role"] for layer in package["layers"]],
                    "qa_status": "approved",
                    "review": package["review"],
                    "sha256": package["psd_sha256"],
                    "width": DEFAULT_ASSET_WIDTH,
                    "height": DEFAULT_ASSET_HEIGHT,
                }
            scene_spec = next((s for s in structure.get("scenes", []) if isinstance(s, dict) and _scene_number(s, 0) == number), {})
            layer_plan = scene_spec.get("local_layer_plan") if isinstance(scene_spec.get("local_layer_plan"), dict) else {}
            image_policy = scene_spec.get("image_generation_policy") if isinstance(scene_spec.get("image_generation_policy"), dict) else {}
            if layer_plan.get("enabled"):
                layer_files = _write_depth_proxy_layers(file_path, layer_dir, number, image_policy)
                uploaded_layers: dict[str, Any] = {
                    "source": "local_depth_proxy_from_single_scene_image",
                    "credit_cost": 0,
                    "method": "soft_target_matte_and_blurred_background_plate",
                    "assets": {},
                }
                for layer_name, layer_path in layer_files.items():
                    layer_object = (f"topics/{topic_id}/layers/scene-{number:03d}-{layer_name}-"
                                    f"{_file_sha256(layer_path)}.png")
                    lbucket, lpath, lurl = _upload_gcs_file(layer_path, layer_object, "image/png")
                    uploaded_layers["assets"][layer_name] = {
                        "storage_provider": "gcs",
                        "bucket": lbucket,
                        "object_path": lpath,
                        "gcs_bucket": lbucket,
                        "gcs_path": lpath,
                        "media_url": lurl,
                        "width": DEFAULT_ASSET_WIDTH,
                        "height": DEFAULT_ASSET_HEIGHT,
                    }
                scene_layer_assets[number] = uploaded_layers

    scenes = structure.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("topic structure has no scenes")
    updated_count = 0
    published_scenes: dict[int, dict[str, Any]] = {}
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        number = _scene_number(scene, index)
        if number in scene_urls:
            gcs_bucket, gcs_path = scene_refs[number]
            image_policy = scene.get("image_generation_policy") if isinstance(scene.get("image_generation_policy"), dict) else {}
            layer_plan = scene.get("local_layer_plan") if isinstance(scene.get("local_layer_plan"), dict) else {}
            scene["image_url"] = scene_urls[number]
            scene["asset_status"] = "ready"
            scene.setdefault("metadata", {})["cowork_image_asset"] = {
                "source": "cowork_builtin_imagegen",
                "storage_provider": "gcs",
                "bucket": gcs_bucket,
                "object_path": gcs_path,
                "gcs_bucket": gcs_bucket,
                "gcs_path": gcs_path,
                "width": DEFAULT_ASSET_WIDTH,
                "height": DEFAULT_ASSET_HEIGHT,
                "credit_policy": {
                    "base_images": int(image_policy.get("base_images") or 1),
                    "generation_unit": image_policy.get("generation_unit") or "2x2_grid_panel",
                    "image_layer_mode": image_policy.get("image_layer_mode") or "hybrid",
                    "additional_images_allowed": int(image_policy.get("additional_images_allowed") or 0),
                    "multi_image_allowed": bool(image_policy.get("multi_image_allowed")),
                    "psd_layer_package_required": bool(image_policy.get("psd_layer_package_required")),
                    "psd_layer_generation_unit": image_policy.get("psd_layer_generation_unit") or "none",
                    "psd_layer_generation_units_estimate": float(image_policy.get("psd_layer_generation_units_estimate") or 0),
                    "api_generation_units_estimate": float(image_policy.get("api_generation_units_estimate") or 0.25),
                    "estimated_generation_credits": float(image_policy.get("estimated_generation_credits") or 0.25),
                    "max_api_generation_units_with_optional_extra": float(image_policy.get("max_api_generation_units_with_optional_extra") or 0.25),
                },
                "local_layer_plan": {
                    "enabled": bool(layer_plan.get("enabled")),
                    "source": layer_plan.get("source") or "",
                    "method": layer_plan.get("method") or "",
                    "credit_cost": int(layer_plan.get("credit_cost") or 0),
                },
            }
            if number in scene_layer_assets:
                scene.setdefault("metadata", {})["local_layer_asset"] = scene_layer_assets[number]
                scene["local_layer_status"] = "ready"
            if number in scene_psd_assets:
                scene.setdefault("metadata", {})["psd_layer_asset"] = scene_psd_assets[number]
                scene["psd_layer_status"] = "ready"
            psd_plan = scene.get("psd_layer_plan") if isinstance(scene.get("psd_layer_plan"), dict) else {}
            if psd_plan:
                scene.setdefault("metadata", {})["psd_layer_plan"] = {
                    "enabled": bool(psd_plan.get("enabled")),
                    "mode": psd_plan.get("mode") or "hybrid",
                    "source": psd_plan.get("source") or "",
                    "method": psd_plan.get("method") or "",
                    "outputs": psd_plan.get("outputs") if isinstance(psd_plan.get("outputs"), list) else [],
                    "credit_cost_estimate": float(psd_plan.get("credit_cost_estimate") or 0),
                }
            published_scenes[number] = scene
            updated_count += 1
    if updated_count != len(scene_urls):
        raise RuntimeError("not every cropped image could be mapped to a topic scene")

    updates = [{
        "scene_number": number,
        "expected_source": manifest_sources[number],
        "expected_assets": expected_assets[number],
        "asset_patch": _scene_asset_patch(published_scenes[number]),
    } for number in sorted(scene_urls)]
    _patch_topic_scene_assets(topic_id, updates, base_url, headers)
    if manifest_layer_specs:
        _propagate_published_template_assets(topic_id, base_url, headers)
    return [scene_urls[number] for number in sorted(scene_urls)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CoWork 이미지 그리드 자르기 및 Supabase 씬 매핑")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="DB의 그리드 프롬프트를 CoWork 작업 매니페스트로 내보냅니다")
    export.add_argument("--topic-id", required=True)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--bucket", default=DEFAULT_BUCKET)
    crop = commands.add_parser("crop", help="그리드를 자른 뒤 1920x1080 씬 이미지로 업스케일합니다")
    crop.add_argument("--manifest", type=Path, required=True)
    crop.add_argument("--input-dir", type=Path, required=True)
    crop.add_argument("--output-dir", type=Path, required=True)
    crop.add_argument("--width", type=int, default=DEFAULT_ASSET_WIDTH)
    crop.add_argument("--height", type=int, default=DEFAULT_ASSET_HEIGHT)
    publish_cmd = commands.add_parser("publish", help="크롭 파일을 Storage와 topics_queue 씬에 저장합니다")
    publish_cmd.add_argument("--manifest", type=Path, required=True)
    publish_cmd.add_argument("--images-dir", type=Path, required=True)
    publish_cmd.add_argument("--create-bucket", action="store_true")
    prepare_cmd = commands.add_parser("prepare-layers", help="독립 PNG 레이어를 검수 대기 PSD 패키지로 만듭니다")
    prepare_cmd.add_argument("--manifest", type=Path, required=True)
    prepare_cmd.add_argument("--images-dir", type=Path, required=True)
    generate_cmd = commands.add_parser("generate-layers", help="검증된 인물 레퍼런스로 독립 PNG 레이어를 생성합니다")
    generate_cmd.add_argument("--manifest", type=Path, required=True)
    generate_cmd.add_argument("--images-dir", type=Path, required=True)
    approve_cmd = commands.add_parser("approve-layers", help="PSD 프리뷰 육안 검수를 기록합니다")
    approve_cmd.add_argument("--manifest", type=Path, required=True)
    approve_cmd.add_argument("--images-dir", type=Path, required=True)
    approve_cmd.add_argument("--reviewer", required=True)
    approve_cmd.add_argument("--note", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "export":
        path = export_manifest(args.topic_id, args.out, args.bucket)
        print(path)
    elif args.command == "crop":
        written = crop_grids(
            args.manifest,
            args.input_dir,
            args.output_dir,
            target_width=args.width,
            target_height=args.height,
        )
        print(
            json.dumps(
                {
                    "cropped_and_upscaled": len(written),
                    "width": args.width,
                    "height": args.height,
                    "output_dir": str(args.output_dir),
                },
                ensure_ascii=False,
            )
        )
    elif args.command == "prepare-layers":
        manifest = _manifest(args.manifest)
        specs = manga_layer_package.scene_specs(manifest.get("scene_specs") or [])
        receipt = manga_layer_package.prepare(args.manifest, args.images_dir, specs)
        print(json.dumps({"prepared": len(receipt["packages"]), "receipt": str(manga_layer_package.receipt_path(args.images_dir))}, ensure_ascii=False))
    elif args.command == "generate-layers":
        receipt = manga_layer_generation.generate_layers(args.manifest, args.images_dir)
        print(json.dumps({"generated_or_provided": len(receipt["jobs"]),
                          "review_required": True,
                          "report": str(manga_layer_generation.report_path(args.images_dir))}, ensure_ascii=False))
    elif args.command == "approve-layers":
        manifest = _manifest(args.manifest)
        specs = manga_layer_package.scene_specs(manifest.get("scene_specs") or [])
        receipt = manga_layer_package.approve(args.manifest, args.images_dir, specs,
                                              reviewer=args.reviewer, note=args.note)
        print(json.dumps({"approved": len(receipt["packages"])}, ensure_ascii=False))
    else:
        urls = publish(args.manifest, args.images_dir, args.create_bucket)
        print(json.dumps({"published": len(urls), "urls": urls}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
