# AIR-0210 Legacy Code Removal

**Date**: 2026-07-07
**Status**: DONE (PR pending merge)

## Objectives
- Confirm zero active references to script_analyzer and director_ai across the entire codebase.
- Delete both deprecated service files and all associated dead code.

## Changes Made
- Deleted app/services/script_analyzer.py
- Deleted app/services/director_ai.py
- Deleted templates/pages/script_analyzer_preview.html
- Deleted templates/pages/director_ai_preview.html
- Deleted scratch/test_script_analyzer.py
- Deleted scratch/test_director_ai.py
- Removed GET /admin/script-analyzer and GET /admin/director-ai from app/routers/pages.py

## Next Sprint
- scene_id 기반 E2E 테스트
- Asset Pipeline 통합 검증
