# AIR-0209 QA Results

| Test Case | Status | Notes |
| --- | --- | --- |
| scene_planner 결과에 scene_count 존재 | PASS | `scene_planner.py` JSON Schema 강제됨 |
| scenes[]에 scene_id 존재 | PASS | `scene_planner.py` JSON Schema 강제됨 |
| scenes[]에 scene_order 존재 | PASS | `scene_planner.py` JSON Schema 강제됨 |
| scenes[]에 scene_summary 존재 | PASS | `scene_planner.py` JSON Schema 강제됨 |
| scenes[]에 scene_situation 존재 | PASS | `scene_planner.py` JSON Schema 강제됨 |
| scenes[]에 scene_purpose 존재 | PASS | `scene_planner.py` JSON Schema 강제됨 |
| image.py가 req.script 기반 씬 재분할을 하지 않음 | PASS | 해당 로직 제거됨 |
| image.py가 scenes[]를 필수 기준으로 사용 | PASS | 누락 시 400 Bad Request 리턴 |
| 2x2 이미지 프롬프트가 scenes 4개 단위로 생성됨 | PASS | `chunking` 및 `generate_image_prompts_for_scenes` 도입됨 |
| scene_id가 이미지 프롬프트 결과까지 유지됨 | PASS | Gemini 응답이 원본 `scene_id` 반환 |
| director_api.py가 director_ai_service를 더 이상 호출하지 않음 | PASS | `prompt_director_service` 로 변경됨 |
| script_api.py가 script_analyzer_service를 더 이상 호출하지 않음 | PASS | `scene_planner_service` 로 변경됨 |
| asset_matching_service.py가 scene_id 기준으로 동작 | PASS | 기존 구현 유지됨 |
| deprecated 파일에 명확한 주석 있음 | PASS | `script_analyzer.py`, `director_ai.py` 최상단에 추가됨 |
