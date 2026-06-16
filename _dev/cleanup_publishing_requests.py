import argparse
import json
import os
import sys

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.web_admin_client import web_admin_client


def fetch_rows():
    try:
        response = web_admin_client.supabase_get(
            "publishing_requests",
            params={"select": "id,status,user_id,metadata,created_at", "order": "created_at.desc"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error while loading publishing_requests: {exc}") from exc
    if response is None or response.status_code != 200:
        body = response.text[:300] if response is not None else "no response"
        raise RuntimeError(f"Failed to load publishing_requests: {body}")
    return response.json() or []


def main():
    parser = argparse.ArgumentParser(description="Inspect or mark invalid publishing_requests rows.")
    parser.add_argument("--mark-rejected", action="store_true", help="Mark invalid rows as rejected instead of dry-run only.")
    args = parser.parse_args()

    try:
        rows = fetch_rows()
    except Exception as exc:
        print(f"error={exc}")
        print("hint=Run this script on your normal local terminal where Supabase access is available.")
        return
    invalid = [row for row in rows if not (row.get("metadata") or {}).get("project_id")]

    print(f"total_rows={len(rows)} invalid_rows={len(invalid)}")
    for row in invalid:
        print(json.dumps({
            "id": row.get("id"),
            "status": row.get("status"),
            "user_id": row.get("user_id"),
            "created_at": row.get("created_at"),
            "metadata": row.get("metadata") or {},
        }, ensure_ascii=False))

    if not args.mark_rejected:
        print("dry_run_only=true")
        return

    updated = 0
    for row in invalid:
        metadata = row.get("metadata") or {}
        metadata["cleanup_note"] = "Marked rejected because project_id is missing."
        response = web_admin_client.supabase_patch(
            "publishing_requests",
            {"status": "rejected", "metadata": metadata},
            params={"id": f"eq.{row.get('id')}"},
            timeout=10,
        )
        if response is not None and response.status_code in (200, 204):
            updated += 1

    print(f"marked_rejected={updated}")


if __name__ == "__main__":
    main()
