# Notion Worker Sync Notes

Date: 2026-08-28
Repo: `D:\Projects\에어스튜디오\mytube_clone_20260828`

## Summary

This update connects AIR Worker history and learning memory to a shared Notion database so multiple content workers can reuse the same learning data.

## What Changed

### 1. Worker Notion settings are now normalized before save

File:
- `worker/worker_config.py`

Change:
- Added normalization for `NOTION_API_KEY` and `NOTION_LEARNING_DATABASE_ID` style pasted values.
- If a user pastes `KEY=value` into the settings page, the code strips the `KEY=` prefix before saving.

Reason:
- Prevents broken `.env` values such as:
  - `NOTION_LEARNING_DATABASE_ID=NOTION_LEARNING_DATABASE_ID=...`

### 2. Past worker history can be backfilled into Notion

File:
- `worker/dashboard_app.py`

Change:
- Added `/api/notion/backfill-history`.
- Collects historical worker outputs from local Hermes result files and job history.
- Builds Notion-ready learning rows from:
  - topic/title
  - category
  - title score
  - script score
  - source job id
  - learning text excerpt
- Supports:
  - `limit`
  - `skip_existing`
  - `dry_run`

Reason:
- Old completed jobs were not automatically written into Notion before this update.
- This API allows importing past work into the shared learning DB.

### 3. Settings page now supports backfill preview and execution

File:
- `worker/dashboard_app.py`

Change:
- Added Notion backfill UI in the settings page:
  - max backfill count input
  - skip-existing checkbox
  - preview button
  - execute button
  - result summary panel
  - inserted/skipped/failed result lists

Reason:
- Lets the operator inspect candidates before writing to Notion.

### 4. Notion write path now adapts to the actual DB schema

File:
- `worker/dashboard_app.py`

Change:
- Reads live Notion database property metadata before backfill.
- Maps values to the real property names/types in the target DB.
- Handles current DB differences such as:
  - title field named `이름` instead of `Name`
  - score fields stored as `rich_text` instead of `number`
- Duplicate detection falls back safely when `Topic Queue ID` is not present as its own property.

Reason:
- The live Notion DB schema did not exactly match the original hardcoded assumptions.

### 5. Worker learning read path now understands the live Notion schema

File:
- `worker/notion_learning.py`

Change:
- Read path now supports:
  - title field `이름`
  - generic first title property fallback
  - numeric parsing from `rich_text` score fields

Reason:
- Without this, the worker could write to Notion but fail to read those same rows back into learning memory.

## Verified Results

Verified on 2026-08-28:

- Worker Notion configuration saved correctly after normalization.
- Notion DB connectivity was verified with the real API.
- Historical backfill executed successfully.
- 4 historical rows were inserted into Notion.
- Re-running preview with duplicate skipping enabled returned the same 4 items as skipped.
- Worker learning fetch successfully read back 4 rows from Notion.

## Current Behavior

If multiple content workers use the same:

- `NOTION_API_KEY`
- `NOTION_LEARNING_DATABASE_ID`

then they can:

- write new learning data into the same Notion DB
- backfill historical jobs into the same Notion DB
- read shared learning rows from the same Notion DB

## Remaining Notes

- Historical jobs are not auto-imported retroactively unless backfill is run.
- Some data is preserved most reliably inside `Learning Text`, because the current Notion DB schema is simplified.
- If the Notion DB schema changes again later, the schema-adaptive mapping should reduce breakage, but major field renames should still be rechecked.
