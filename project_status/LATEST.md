# Latest Worknote

Date: 2026-07-07
Repo: C:\Projects\AIR-Studio

## Current understanding
- AIR Studio is a local FastAPI application with a Next.js admin app.
- Current main HEAD includes AIR-0209 Planning Scene Contract Refactor.
- Scene Source of Truth is now the planning stage (scene_planner.py).
- Next available Task ID: AIR-0210

## What changed recently
### AIR-0209 Planning Scene Contract Refactor (2026-07-07, MERGED PR #65)
- Enforced Scene Source of Truth from scene_planner.py through all downstream services.
- pp/routers/image.py no longer splits scripts; uses 4-chunking based on scenes[].
- Removed script_analyzer.py and director_ai.py (deprecated).
- scenes[] arrays with immutable scene_id and scene_order are now mandatory inputs for image/video prompt pipelines.
- Updated media.py schema for PromptsGenerateRequest.
- Added docs/SCENE_SOURCE_OF_TRUTH.md and docs/QA_AIR_0209.md.

## Next Sprint
- Deprecated 코드 완전 제거
- scene_id 기반 E2E 테스트
- Asset Pipeline 통합 검증
