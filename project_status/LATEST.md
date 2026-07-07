# Latest Worknote

Date: 2026-07-07
Repo: C:\Projects\AIR-Studio

## Current understanding
- AIR Studio is a local FastAPI application with a Next.js admin app.
- Current main HEAD includes AIR-0209 Planning Scene Contract Refactor.
- Scene Source of Truth is now the planning stage (scene_planner.py).
- Next available Task ID: AIR-0211

## What changed recently
### AIR-0210 Legacy Code Removal (2026-07-07, PR pending)
- Deleted app/services/script_analyzer.py (deprecated since AIR-0209)
- Deleted app/services/director_ai.py (deprecated since AIR-0209)
- Deleted templates/pages/script_analyzer_preview.html
- Deleted templates/pages/director_ai_preview.html
- Deleted scratch/test_script_analyzer.py
- Deleted scratch/test_director_ai.py
- Removed GET /admin/script-analyzer and GET /admin/director-ai routes from app/routers/pages.py
- Reference search confirmed 0 remaining references after deletion.

### AIR-0209 Planning Scene Contract Refactor (2026-07-07, MERGED PR #65)
- Enforced Scene Source of Truth from scene_planner.py through all downstream services.
- app/routers/image.py no longer splits scripts; uses 4-chunking based on scenes[].
- Removed script_analyzer.py and director_ai.py (deprecated).
- scenes[] arrays with immutable scene_id and scene_order are now mandatory inputs for image/video prompt pipelines.
- Updated media.py schema for PromptsGenerateRequest.
- Added docs/SCENE_SOURCE_OF_TRUTH.md and docs/QA_AIR_0209.md.

## Next Sprint
- scene_id 기반 E2E 테스트 (기획부터 에셋 매칭까지 파이프라인 무결성 검증)
- Asset Pipeline 통합 검증
