# Scene Source of Truth Policy

## 개요
AIR Studio의 AI 파이프라인에서 "Scene"은 전체 영상의 구조와 흐름을 결정짓는 핵심 단위입니다.
AIR-0209 리팩토링을 통해 Scene의 분할 및 구성 기준에 대한 **Source of Truth(단일 진실 공급원)** 정책을 확정합니다.

## 핵심 원칙
1. **기획 단계가 유일한 Source of Truth입니다.**
   - `scene_planner.py`를 통해 생성된 `scenes[]` 배열이 전체 파이프라인의 기준이 됩니다.
   - 대본 생성, 이미지 프롬프트 생성, 영상 프롬프트 생성, 애셋 매칭, 최종 타임라인 렌더링까지 모두 이 `scenes[]`의 경계와 `scene_id`, `scene_order`를 변경 없이 사용해야 합니다.

2. **하위 단계에서의 Scene 재분할 엄격 금지**
   - 기존처럼 긴 텍스트 대본(`req.script`)을 LLM에게 통째로 넘겨 하위 모듈이 임의로 씬을 다시 쪼개는 행위를 엄격히 금지합니다.
   - `[DEPRECATED]` `script_analyzer.py` 및 구형 `director_ai.py`는 더 이상 사용되지 않습니다.

3. **2x2 이미지 프롬프트 Chunk 생성**
   - 이미지 프롬프트 등 다량의 씬 처리가 필요한 경우, 기획 단계에서 확정된 `scenes[]`를 4개 단위(Chunk)로 나누어 병렬 처리합니다.
   - 이 때도 각 씬의 `scene_id`는 고유하게 유지되며 프롬프트 생성 결과에 그대로 매핑되어 반환되어야 합니다.

## 파이프라인 데이터 흐름
`Topic` -> `Scene Planner (scenes[])` -> `Script Generator (Fill dialogue/narration)` -> `Prompt Director (Fill image/video prompts)` -> `Asset Matching (Match by scene_id)` -> `Timeline & Render`
