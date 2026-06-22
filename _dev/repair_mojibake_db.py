"""Repair reversible Korean mojibake in the local SQLite DB.

Usage:
    python _dev/repair_mojibake_db.py --dry-run
    python _dev/repair_mojibake_db.py --apply

The script creates a backup before applying changes and only updates text values
that look like mojibake and can be round-tripped safely.
"""
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config

DB_PATH = Path(config.DB_PATH)
MOJIBAKE_MARKERS = ("�", "紐", "吏", "諛", "異", "媛", "깆", "떊", "쒗", "묐", "씠", "섏", "꾩", "젣", "濡", "ㅻ", "좎", "뺣")
TEXT_TABLES = {
    "projects": ["name", "topic", "status", "language", "name_vi", "topic_vi"],
    "project_settings": None,
    "scripts": ["full_script"],
    "script_structure": ["hook", "sections", "cta", "style"],
    "image_prompts": ["scene_text", "prompt_ko", "prompt_en", "script_start", "script_end", "scene_title", "motion_desc", "sfx_prompt", "bgm_prompt", "prompt_char", "prompt_bg", "flow_prompt", "prompt_en_start", "prompt_en_end", "scene_text_vi"],
    "metadata": ["titles", "description", "tags", "hashtags"],
    "thumbnails": ["ideas", "texts", "full_settings"],
    "project_sources": ["title", "content", "url"],
    "project_characters": ["name", "role", "description_ko", "prompt_en", "dna_yaml"],
}


def looks_broken(value: str) -> bool:
    return any(marker in value for marker in MOJIBAKE_MARKERS)


def try_fix_text(value: str) -> Tuple[str, bool]:
    if not value or not looks_broken(value):
        return value, False
    for source_encoding in ("cp949", "euc-kr", "latin1"):
        try:
            fixed = value.encode(source_encoding, errors="strict").decode("utf-8", errors="strict")
        except Exception:
            continue
        if fixed != value and not looks_broken(fixed):
            return fixed, True
    return value, False


def fix_json_leaf(value: Any) -> Tuple[Any, bool]:
    changed = False
    if isinstance(value, str):
        return try_fix_text(value)
    if isinstance(value, list):
        out = []
        for item in value:
            fixed, item_changed = fix_json_leaf(item)
            out.append(fixed)
            changed = changed or item_changed
        return out, changed
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            fixed, item_changed = fix_json_leaf(item)
            out[key] = fixed
            changed = changed or item_changed
        return out, changed
    return value, False


def fix_value(value: Any) -> Tuple[Any, bool]:
    if not isinstance(value, str) or not value:
        return value, False
    stripped = value.strip()
    if stripped.startswith(("{", "[")):
        try:
            parsed = json.loads(value)
            fixed, changed = fix_json_leaf(parsed)
            if changed:
                return json.dumps(fixed, ensure_ascii=False), True
        except Exception:
            pass
    return try_fix_text(value)


def table_columns(conn, table: str):
    try:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write changes to the DB")
    parser.add_argument("--dry-run", action="store_true", help="scan only")
    args = parser.parse_args()
    apply = args.apply and not args.dry_run

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    backup_path = None
    if apply:
        backup_path = DB_PATH.with_name(f"{DB_PATH.stem}.mojibake-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{DB_PATH.suffix}")
        shutil.copy2(DB_PATH, backup_path)
        print(f"Backup created: {backup_path}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    changes = []

    try:
        for table, configured_cols in TEXT_TABLES.items():
            cols = table_columns(conn, table)
            if not cols or "id" not in cols:
                continue
            text_cols = configured_cols or [c for c in cols if c not in ("id", "project_id") and not c.endswith("_id")]
            text_cols = [c for c in text_cols if c in cols]
            if not text_cols:
                continue
            for row in conn.execute(f"SELECT id, {', '.join(text_cols)} FROM {table}").fetchall():
                updates = {}
                for col in text_cols:
                    fixed, changed = fix_value(row[col])
                    if changed:
                        updates[col] = fixed
                        changes.append((table, row["id"], col, row[col], fixed))
                if apply and updates:
                    set_clause = ", ".join([f"{col} = ?" for col in updates])
                    conn.execute(
                        f"UPDATE {table} SET {set_clause} WHERE id = ?",
                        [*updates.values(), row["id"]],
                    )
        if apply:
            conn.commit()
    finally:
        conn.close()

    print(f"Detected repairable values: {len(changes)}")
    for table, row_id, col, before, after in changes[:50]:
        print(f"[{table}#{row_id}.{col}] {str(before)[:80]} -> {str(after)[:80]}")
    if len(changes) > 50:
        print(f"... {len(changes) - 50} more")
    if apply:
        print("Applied changes.")
    else:
        print("Dry run only. Re-run with --apply to update the DB.")


if __name__ == "__main__":
    main()
