# AIR STD Codex old-story topic 3341 handoff

Date: 2026-09-06  
Repository baseline requested by user: `aa6f5da`  
Production repository: `ibnetsoft/mytube`  
Production site: `https://mytube-ashy-seven.vercel.app`

## Summary

Codex generated and published one prepared CoWork/STD topic for the `옛날이야기` category, then updated the user web so the topic appears on the STD topic page and can be selected by another user.

Topic:

- `topics_queue.id`: `3341`
- Title: `새벽 종을 훔친 아이`
- Category: `옛날이야기`
- `category_id`: `2`
- Duration: `5` minutes
- Estimated payout: `$3.00 USDT`
- Scene count: `28`
- Required video scenes: `1~12`
- Image scenes: `13~28`
- Image style: `watercolor forest story`
- Current public/claimable state: `status=pending`, `assigned_employee_email=""`, `assigned_at=null`

## Generated data saved in Supabase

Primary row:

- Table: `topics_queue`
- Row id: `3341`

Important fields:

- `generated_title`: `새벽 종을 훔친 아이`
- `topic`: original topic text
- `category_id`: `2`
- `recommended_duration_minutes`: `5`
- `estimated_payout`: `3`
- `total_scenes`: `28`
- `video_scenes`: `12`
- `image_scenes`: `16`
- `assigned_image_style`: `watercolor forest story`
- `pregenerated_script`: full generated Korean story script
- `pregenerated_structure.scenes`: 28 scene records
- `pregenerated_structure.image_grid_prompts`: 7 strict 2x2 image-grid prompts
- `publish_metadata`: YouTube-style titles, description, tags, and hashtags
- `progress_payload`: generation metadata and learning/publish state

Scene data structure:

- Scenes `1~12`
  - `target_duration`: 5 seconds each
  - `video_prompt_required`: true
  - `video_prompt`: present
  - `image_prompt`: present
  - `image_url`: present for generated/cropped still reference image
- Scenes `13~28`
  - image-oriented scene beats
  - `image_prompt`: present
  - `image_url`: present

Storage:

- Generated/cropped scene stills were uploaded to Supabase Storage under:
  - `content-assets/topics/3341/images/scene-001.png`
  - ...
  - `content-assets/topics/3341/images/scene-028.png`

## Notion learning record

The topic was also stored in the Notion learning database.

- Notion page: `https://app.notion.com/p/3d336967d21b816aa995ce4fa23fdd0a`
- Title: `새벽 종을 훔친 아이`
- Category: `옛날이야기`
- Quality outcome: `pass`
- Title score: `91`
- Script score: `91`

Trace identifiers were backfilled so the Notion row can be tied back to Supabase and the worker job:

- `Topic Queue ID`: `3341`
- `Source Job Key`: `6c40e792-4909-43d5-b26d-f5e7b61f42fd`
- `Category ID`: `2`

## User-web visibility work

The STD topic page did not initially show the prepared topic consistently because the topic API depended on a relationship join/fallback path that could miss the direct `topics_queue` row.

Fix:

- File: `auth-web/app/api/std/topics/route.ts`
- Commit: `b188d46 Fix STD direct topic refresh visibility`
- Change: query `topics_queue` directly for prepared STD topics, then attach category metadata separately.
- Verification at the time of deployment: production `/api/std/topics?refresh=1...` returned topic id `3341`.

## Follow-up fixes made around this topic

These fixes were made while testing the same CoWork/STD flow:

- `20b598c Fix STD video scene asset uploads`
  - Server-side asset upload route for scene media.
  - 1~12 scenes reject `image` uploads and require `video`.
- `de10913 Fix large STD video uploads`
  - Large MP4 files avoid Vercel body-size failures by using Google Drive resumable upload.
- `107dc95 Add Opera fallback for STD video uploads`
  - If the browser blocks direct Google Drive upload, retry via 2 MB server-mediated chunks.
- `feb896a Respect short STD scene counts for subtitles`
  - 5-minute/28-scene projects no longer expand subtitle timing into the legacy 53-scene longform layout.

## Current expected CoWork behavior

For topic `3341`:

1. Topic appears on the STD topic page as a selectable `옛날이야기` task.
2. Claiming creates a `std_projects` row and `std_project_scenes` rows.
3. The Image tab shows 28 scenes only.
4. Scenes `1~12` require uploaded/generated video files before the first-minute video gauge is complete.
5. Image upload does not count for scenes `1~12`.
6. Scenes `13~28` can use image assets.
7. Subtitle generation respects the 28-scene structure instead of creating fake scenes `29~53`.

