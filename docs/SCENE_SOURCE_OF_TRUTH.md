# Scene Source of Truth

> **이 문서는 AIR Studio의 영상 기획 및 생성 파이프라인에서 "Scene"의 역할과 기준을 정의하는 핵심 아키텍처 문서입니다.**

## 1. Scene 기준 정의
- **Source of Truth (유일한 기준점)**: Scene 구조는 "기획 단계(Planning AI)"에서 최초이자 최종으로 확정됩니다.
- 한 번 확정된 Scene의 배열(`scenes[]`), 순서(`scene_order`), 각 Scene의 목표 시간(`estimated_seconds`), ID(`scene_id`)는 후속 파이프라인에서 절대 임의로 분할되거나 병합되거나 변경될 수 없습니다.
- 대본 생성, 2x2 이미지 프롬프트 생성, 영상 프롬프트 생성, 에셋 매칭, 최종 타임라인 조립 등 모든 단계는 이 **확정된 Scene**을 1차 기준으로 삼아 동작해야 합니다.

## 2. Shot (shot_hints) 정의
- **독립 단위 아님**: "Shot"은 더 이상 Scene을 나누는 독립적인 구조 단위가 아닙니다.
- **보조 연출 정보**: Scene 내부에서 카메라 워크, 구도, 인물 강조 등을 지시하기 위한 하위 보조 정보(Array)로만 사용되며, 코드상에서는 `shot_hints`로 명명하여 의미를 명확히 합니다.
- **예시**:
  ```json
  "shot_hints": [
    {
      "id": "hint001",
      "camera": "close-up",
      "composition": "rule of thirds",
      "movement": "slow push-in",
      "emotion": "sad",
      "purpose": "emphasize character emotion"
    }
  ]
  ```

## 3. 금지되는 재분할 패턴
- **Script Analyzer**: 이미 확정된 기획 Scene이 있음에도 불구하고, 완성된 대본 텍스트를 AI에 넣어 새로운 Scene으로 재분할하는 행위 (절대 금지).
- **Director AI**: 하나의 Scene을 2개 이상의 시간 할당된 Shot으로 쪼개어 후속 파이프라인(Production Planner, Asset Matching)이 Scene 대신 Shot을 바라보게 만드는 행위 (절대 금지).
- **Timeline / Asset Matching**: `shot_id`를 핵심 기준으로 사용하여 에셋을 매칭하고 편집 타임라인을 나누는 행위 (보조 참고용으로만 사용).

## 4. 각 서비스의 책임
- **Scene Planner (구 Script Analyzer)**: 주제를 바탕으로 **Scene 구조를 최초 확정**합니다.
- **Script Generator**: 확정된 Scene 구조 내부에 **대본(Script text)만 채워 넣습니다**.
- **Prompt Director (구 Director AI)**: 확정된 Scene 구조를 분할하지 않고, Scene 전체의 `image_prompt`, `video_prompt`, `lighting_hint` 및 `shot_hints`를 **보강(Enhance)만 합니다**.
- **Production Planner**: `scenes` 배열을 순회하며 에셋 생성 계획을 수립합니다.
- **Asset Matching**: 업로드된 에셋을 `scenes` 구조에 매칭합니다. (DB의 `scene_id`가 핵심)
