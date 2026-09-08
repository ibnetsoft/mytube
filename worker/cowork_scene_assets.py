"""Prepare, crop, and publish CoWork-generated storyboard image grids.

This script deliberately does not call an image-generation API.  A CoWork
agent uses the built-in image tool for each exported grid prompt, then this
script crops the returned grids and persists the scene mapping in Supabase.
"""

from __future__ import annotations

import argparse
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
from PIL import ImageFilter
from PIL import ImageOps


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUCKET = "content-assets"
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


def _topic(topic_id: str) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, str]]:
    base_url, headers = _supabase()
    safe_id = quote(topic_id, safe="")
    response = _request(
        "GET",
        f"{base_url}/rest/v1/topics_queue?id=eq.{safe_id}&select=id,topic,generated_title,pregenerated_structure,pregenerated_structure_status",
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


def export_manifest(topic_id: str, destination: Path, bucket: str) -> Path:
    row, structure, _, _ = _topic(topic_id)
    scenes = structure.get("scenes")
    grids = structure.get("image_grid_prompts")
    if not isinstance(scenes, list) or not scenes:
        raise RuntimeError("topic has no scenes")
    if not isinstance(grids, list) or not grids:
        raise RuntimeError("topic has no image_grid_prompts")

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
        "grids": manifest_grids,
    }
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def _manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "cowork_scene_assets/v1":
        raise ValueError("not a CoWork scene-assets manifest")
    if not isinstance(data.get("grids"), list) or not data.get("topic_id"):
        raise ValueError("manifest is incomplete")
    return data


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
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    assigned: set[int] = set()
    for grid in manifest["grids"]:
        raw_path = input_dir / str(grid["raw_file"])
        if not raw_path.is_file():
            raise FileNotFoundError(f"generated grid is missing: {raw_path}")
        scene_numbers = grid.get("scene_numbers")
        if not isinstance(scene_numbers, list) or len(scene_numbers) != 4:
            raise ValueError(f"grid {grid.get('grid_number')} does not map exactly four scenes")
        with Image.open(raw_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            width, height = image.size
            if width < 4 or height < 4:
                raise ValueError(f"grid {raw_path.name} is too small to crop")
            x_mid, y_mid = width // 2, height // 2
            boxes = ((0, 0, x_mid, y_mid), (x_mid, 0, width, y_mid), (0, y_mid, x_mid, height), (x_mid, y_mid, width, height))
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
                if target.exists():
                    raise FileExistsError(f"refusing to overwrite existing crop: {target}")
                _upscale_panel(image.crop(box), target_width, target_height).save(
                    target, format="PNG", optimize=True
                )
                written.append(target)
    return written


def _ensure_bucket(base_url: str, headers: dict[str, str], bucket: str) -> None:
    response = requests.get(
        f"{base_url}/storage/v1/bucket/{quote(bucket, safe='')}", headers=headers, timeout=60
    )
    if response.status_code == 200:
        return
    # Some Supabase Storage gateways return an HTTP 400 envelope whose
    # payload still identifies this as the normal missing-bucket condition.
    # Treat only that documented NoSuchBucket payload like a 404; other 400s
    # (authentication, malformed bucket id, etc.) must remain hard failures.
    missing_bucket = response.status_code == 404
    if response.status_code == 400:
        try:
            missing_bucket = response.json().get("code") == "NoSuchBucket"
        except ValueError:
            missing_bucket = False
    if not missing_bucket:
        raise RuntimeError(f"Storage bucket lookup failed ({response.status_code}): {response.text[:500]}")
    _request(
        "POST",
        f"{base_url}/storage/v1/bucket",
        {**headers, "Content-Type": "application/json"},
        json={"id": bucket, "name": bucket, "public": True},
    )


def publish(manifest_path: Path, images_dir: Path, create_bucket: bool) -> list[str]:
    manifest = _manifest(manifest_path)
    topic_id = str(manifest["topic_id"])
    bucket = str(manifest.get("bucket") or DEFAULT_BUCKET)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
        raise ValueError("bucket must be a safe lowercase storage bucket name")
    row, structure, base_url, headers = _topic(topic_id)
    if create_bucket:
        _ensure_bucket(base_url, headers, bucket)

    scene_urls: dict[int, str] = {}
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
            object_path = f"topics/{topic_id}/images/scene-{number:03d}.png"
            mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
            with file_path.open("rb") as handle:
                _request(
                    "POST",
                    f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}",
                    # Stable object keys make a failed publish safely retryable.
                    {**headers, "Content-Type": mime_type, "x-upsert": "true"},
                    data=handle,
                )
            scene_urls[number] = f"{base_url}/storage/v1/object/public/{bucket}/{object_path}"

    scenes = structure.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("topic structure has no scenes")
    updated_count = 0
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        number = _scene_number(scene, index)
        if number in scene_urls:
            scene["image_url"] = scene_urls[number]
            scene["asset_status"] = "ready"
            scene.setdefault("metadata", {})["cowork_image_asset"] = {
                "source": "cowork_builtin_imagegen",
                "bucket": bucket,
                "object_path": f"topics/{topic_id}/images/scene-{number:03d}.png",
                "width": DEFAULT_ASSET_WIDTH,
                "height": DEFAULT_ASSET_HEIGHT,
            }
            updated_count += 1
    if updated_count != len(scene_urls):
        raise RuntimeError("not every cropped image could be mapped to a topic scene")

    _request(
        "PATCH",
        f"{base_url}/rest/v1/topics_queue?id=eq.{quote(topic_id, safe='')}",
        {**headers, "Content-Type": "application/json", "Prefer": "return=representation"},
        json={"pregenerated_structure": structure},
    )
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
