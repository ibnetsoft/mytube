"""Export and publish a CoWork-generated thumbnail background for a prepared topic.

This helper never calls an image API.  The Codex worker supplies
``thumbnail_image_prompt``; CoWork's image tool renders it, then this script
verifies, uploads, and links the resulting background for thumbnail preview.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from PIL import Image, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parent.parent
BUCKET = "content-assets"
WIDTH, HEIGHT = 1920, 1080


def _client() -> tuple[str, dict[str, str]]:
    load_dotenv(ROOT / ".env", override=True)
    base_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base_url or not key:
        raise RuntimeError("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return base_url, {"apikey": key, "Authorization": f"Bearer {key}"}


def _topic(topic_id: str) -> tuple[dict[str, Any], str, dict[str, str]]:
    base_url, headers = _client()
    response = requests.get(
        f"{base_url}/rest/v1/topics_queue?id=eq.{quote(str(topic_id), safe='')}&select=id,progress_payload",
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"topics_queue row not found for id={topic_id}")
    return rows[0], base_url, headers


def export_prompt(topic_id: str, output_path: Path) -> Path:
    row, _, _ = _topic(topic_id)
    progress = row.get("progress_payload") if isinstance(row.get("progress_payload"), dict) else {}
    prompt = str(progress.get("thumbnail_image_prompt") or "").strip()
    if len(prompt) < 80:
        raise RuntimeError("topic has no Codex-generated thumbnail_image_prompt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "schema": "cowork_thumbnail_asset/v1",
                "topic_id": str(row["id"]),
                "prompt": prompt,
                "output": {
                    "width": WIDTH,
                    "height": HEIGHT,
                    "text_in_image": False,
                    "storage_object": f"topics/{row['id']}/thumbnail/background.png",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


def _ensure_bucket(base_url: str, headers: dict[str, str]) -> None:
    check = requests.get(f"{base_url}/storage/v1/bucket/{BUCKET}", headers=headers, timeout=60)
    if check.status_code == 200:
        return
    if check.status_code not in (400, 404):
        raise RuntimeError(f"Storage bucket lookup failed: {check.status_code} {check.text[:300]}")
    create = requests.post(
        f"{base_url}/storage/v1/bucket",
        headers={**headers, "Content-Type": "application/json"},
        json={"id": BUCKET, "name": BUCKET, "public": True},
        timeout=60,
    )
    if create.status_code not in (200, 201, 409):
        raise RuntimeError(f"Storage bucket creation failed: {create.status_code} {create.text[:300]}")


def _thumbnail_metadata(progress: dict[str, Any], public_url: str) -> dict[str, Any]:
    """Build one canonical thumbnail result payload for queue and claimed projects."""
    return {
        **progress,
        "thumbnail_bg_url": public_url,
        "thumbnail_bg_width": WIDTH,
        "thumbnail_bg_height": HEIGHT,
        "thumbnail_bg_source": "cowork_imagegen",
        "thumbnail_generation_status": "completed",
    }


def _sync_claimed_std_projects(
    topic_id: str,
    public_url: str,
    base_url: str,
    headers: dict[str, str],
) -> int:
    """Make a newly rendered background visible to projects already claimed on STD web.

    Claiming intentionally snapshots ``topics_queue.progress_payload`` into
    ``std_projects``.  Therefore publishing a CoWork image later must update
    that snapshot as well; otherwise a browser reload can never see it.
    """
    rows_response = requests.get(
        f"{base_url}/rest/v1/std_projects",
        headers=headers,
        params={
            "topic_queue_id": f"eq.{topic_id}",
            "select": "id,project_payload,progress_payload",
        },
        timeout=60,
    )
    rows_response.raise_for_status()
    rows = rows_response.json()
    if not isinstance(rows, list):
        raise RuntimeError("std_projects lookup returned an invalid response")

    synced = 0
    for project in rows:
        if not isinstance(project, dict) or not project.get("id"):
            continue
        project_payload = project.get("project_payload") if isinstance(project.get("project_payload"), dict) else {}
        progress_payload = project.get("progress_payload") if isinstance(project.get("progress_payload"), dict) else {}
        project_patch = _thumbnail_metadata(project_payload, public_url)
        progress_patch = _thumbnail_metadata(progress_payload, public_url)
        update = requests.patch(
            f"{base_url}/rest/v1/std_projects?id=eq.{quote(str(project['id']), safe='')}",
            headers={**headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"project_payload": project_patch, "progress_payload": progress_patch},
            timeout=60,
        )
        if update.status_code not in (200, 204):
            raise RuntimeError(
                f"claimed STD project thumbnail update failed: {update.status_code} {update.text[:300]}"
            )
        synced += 1
    return synced


def publish(topic_id: str, source_path: Path, *, create_bucket: bool = False) -> str:
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    row, base_url, headers = _topic(topic_id)
    if create_bucket:
        _ensure_bucket(base_url, headers)
    with Image.open(source_path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        source_ratio = image.width / image.height
        target_ratio = WIDTH / HEIGHT
        if source_ratio > target_ratio:
            crop_width = round(image.height * target_ratio)
            left = (image.width - crop_width) // 2
            image = image.crop((left, 0, left + crop_width, image.height))
        elif source_ratio < target_ratio:
            crop_height = round(image.width / target_ratio)
            top = (image.height - crop_height) // 2
            image = image.crop((0, top, image.width, top + crop_height))
        prepared = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).filter(
            ImageFilter.UnsharpMask(radius=1.2, percent=105, threshold=3)
        )
    output_path = source_path.with_suffix(".thumbnail-bg.png")
    prepared.save(output_path, format="PNG", optimize=True)
    object_path = f"topics/{row['id']}/thumbnail/background.png"
    with output_path.open("rb") as handle:
        upload = requests.post(
            f"{base_url}/storage/v1/object/{BUCKET}/{quote(object_path, safe='/')}",
            headers={**headers, "Content-Type": mimetypes.guess_type(output_path.name)[0] or "image/png", "x-upsert": "true"},
            data=handle,
            timeout=120,
        )
    if upload.status_code not in (200, 201):
        raise RuntimeError(f"thumbnail upload failed: {upload.status_code} {upload.text[:300]}")
    public_url = f"{base_url}/storage/v1/object/public/{BUCKET}/{object_path}"
    progress = row.get("progress_payload") if isinstance(row.get("progress_payload"), dict) else {}
    patch = _thumbnail_metadata(progress, public_url)
    update = requests.patch(
        f"{base_url}/rest/v1/topics_queue?id=eq.{quote(str(row['id']), safe='')}",
        headers={**headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
        json={"progress_payload": patch},
        timeout=60,
    )
    if update.status_code not in (200, 204):
        raise RuntimeError(f"thumbnail URL update failed: {update.status_code} {update.text[:300]}")
    _sync_claimed_std_projects(str(row["id"]), public_url, base_url, headers)
    return public_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Export/publish a CoWork thumbnail background")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--topic-id", required=True)
    export.add_argument("--out", required=True, type=Path)
    publish_cmd = commands.add_parser("publish")
    publish_cmd.add_argument("--topic-id", required=True)
    publish_cmd.add_argument("--image", required=True, type=Path)
    publish_cmd.add_argument("--create-bucket", action="store_true")
    args = parser.parse_args()
    if args.command == "export":
        print(export_prompt(args.topic_id, args.out))
    else:
        print(publish(args.topic_id, args.image, create_bucket=args.create_bucket))


if __name__ == "__main__":
    main()
