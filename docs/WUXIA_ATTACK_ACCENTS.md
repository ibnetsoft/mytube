# 선택적 전기 방전·공격 궤적·접촉 섬광

`wuxia_attack_accent/v1`은 실제 검토된 공격에만 붙이는 연출이다. 기존 확정 회차를 자동 변경하거나 모든 컷에 효과 묶음을 적용하지 않는다. 새로운 대본 생성 설정 확인 규칙도 그대로 유지한다.

## 실행 경로

- 패키지 씬의 `effects`에 선택한 효과를 저장한다. `stdWuxiaEffects.ts`가 편집 시계/확정 음성 앵커에서 도형을 계산하며, 실제 `StdWuxiaScenePreview`가 표시한다.
- `freezeWuxiaScene`은 그 결과를 기존 `wuxia_native_timeline/v3` 이상에 프레임별로 저장한다. 추가 네이티브 도형이나 AE 전용 랜덤 효과를 사용하지 않는다. 도형은 최대 64점의 경계가 제한된 다각형이며 순서·색·투명도·시각을 그대로 실행한다.
- 통합워커 `wuxia_effects.validate_samples`는 새 효과의 원화 SHA·접촉 순서·보호 영역도 확인한다. `wuxia_native_timeline.jsx`는 동일한 동결 도형을 AE Shape Layer로 만든다. 검수된 원본·입 패치·대사 글자는 보존한다.

## 효과와 타이밍

- `attack_speedline`: 실제 주먹/검날 이동을 따르는 2–4개 정규화 좌표의 `attack_path`. 최대 0.35초 동안 접촉 **직전**에 흐른 뒤 접촉 시점에서 끝난다. 검은 휘두르는 호, 주먹은 뻗는 방향을 따라 기록한다. 방사형 집중선을 공격 방향선으로 대체했다고 보고하지 않는다.
- `contact_flash`: 접촉부터 시작하는 단일 펄스, 최대 0.125초. `flash_scope: local`은 노란 광채와 흰 중심, `screen`은 최대 불투명도 0.22의 짧은 연노랑 노출 변화다. 얼굴 보호 상자를 잘라 사각형 구멍을 만들지 않는다. 별도 `screen_flash_reviewed:true`가 필요하다. 워커는 `exposure_wash/v1`에 한해 정확한 전체 화면 사각형·색상·불투명도·타입을 검증한 후 보호 영역의 저강도 노출 변화를 허용한다. 불투명 번개는 계속 얼굴·문자를 피한다. 권장 시작값은 출력 1–2프레임이며 반복 화면 점멸을 만들지 않는다.
- `electric_discharge`: 실제 전기/전격 표현에 근거가 있는 장면만 사용한다. 최대 0.6초. 접촉점에서 밖으로 자라는 불규칙한 테이퍼 줄기·가는 잔가지·흰 중심과 여러 겹의 낮은 불투명도 황색 광채를 겹친다. 일정한 굵기의 사각 띠를 이어 붙이지 않는다. 편집 프레임에 묶인 최대 약 16Hz 분기 변화를 만든다. 정지/탐색에서도 같은 도형을 돌려준다. 필요하면 `delay_seconds`로 플래시 직후에 시작한다. 일반 칼질에 전기 능력을 임의로 만들지 않는다.
- 세 효과를 전부 쓸 필요는 없다. `duration_seconds`, `intensity`(0–1), `radius`(0–1)를 사건에 맞게 선택한다. `center`는 검토된 실제 접촉점이며 경로 끝과 일치해야 한다.
- 음성 앵커는 `action_review.timing_basis: voice_anchor`, 기존 `voice_binding.exact_anchor`와 `quote`를 사용한다. 무발화 동작은 `scene_local`과 씬 시작 기준 `contact_at_seconds`를 명시한다. 근거 없는 `preview_at` 추정으로 새 효과의 접촉 시각을 대신하지 않는다. 이동·상태 컷이 실제로 있는지 검토하며 효과만으로 정지 인물이 공격한 것처럼 승인하지 않는다.

## 실제 원화 준비

`worker.wuxia_attack_accents.attach(package, selections, source_root)` 또는 아래 CLI는 새 패키지 사본에 검토한 선택만 연결한다. 원본 PNG SHA를 대조하며 원본/출력 덮어쓰기를 하지 않는다. 같은 상태를 다시 준비할 때 이 계약이 만든 효과만 교체하고 기존 수동 효과는 보존한다. 빈 효과 선택은 정상이다.

```sh
python -m worker.wuxia_attack_accents --package episode-package.json \
  --review reviewed-attacks.json --source-root reviewed-images \
  --output episode-package-with-accents.json
```

검토 파일은 아래 구조의 배열이다. 모든 좌표는 1920×1080 기준 정규화 좌표다. 이 예시는 데이터 형식이며 실제 원화/타이밍 승인 증거가 아니다.

```json
[{
  "scene_id": "E05_S08", "asset_id": "E05_S08_STATE_02", "source_file": "state-02.png",
  "review": {
    "contract": "wuxia_attack_accent/v1", "source_sha256": "실제 PNG SHA256",
    "source_reviewed": true, "event": "실제 묘사된 사건", "materials": "접촉 재질",
    "reason": "이 컷에 선택한 이유", "motion_evidence": "이전/현재 상태의 실제 이동·접촉 근거",
    "timing_basis": "scene_local", "protected_boxes": [[0.1, 0.1, 0.3, 0.35]],
    "electricity_motivated": false, "screen_flash_reviewed": false
  },
  "effects": [{
    "type": "attack_speedline", "attack_path": [[0.3, 0.7], [0.7, 0.65]],
    "center": [0.7, 0.65], "contact_at_seconds": 1.0,
    "duration_seconds": 0.25, "intensity": 0.9, "radius": 0.4
  }]
}]
```

실제 얼굴은 상태의 `face_exclusion_boxes`로, 손·중요 무기·원화에 박힌 글자는 `protected_boxes`로 검토한다. 웹의 현재 편집 글자도 자동 보호한다. 효과음 문구는 실제 사건/재질/접촉에서 정하고 기존 편집 가능한 타이포를 쓴다. “직”을 모든 공격에 복사하거나 화면 전용 글자를 TTS/입모양에 넣지 않는다. 불확실한 선택은 근거와 품질 노트를 남기고 적용하지 않으며, 생성/검증 실패를 빈 효과 성공으로 바꾸지 않는다.

준비한 사본은 기존 회차 패키지 등록 경로로 반영한 뒤 웹 읽기와 실제 재생을 확인한다. CLI 출력만으로 등록·실제 AE 검수가 끝났다고 보고하지 않는다.

## 검증 구분

- `auth-web/tests/std-wuxia-attack-accents.cjs`: 접촉 전후, 방향, 결정론, 원화 보호 및 동결→워커 검증→AE JSX 도형 동등성.
- `tests/test_wuxia_attack_accents.py`: 원본 보존, SHA, 선택별 재준비, 접촉 순서와 보호 영역 실패.
- `node scripts/verify_wuxia_attack_accents.cjs`: **실제 웹 컴포넌트**의 기술 도해 48프레임과 AE 동결 입력을 대조한다. `preview.html`, PNG, `frozen-timeline.json`, AE 코드 조각, 검증 JSON을 별도 출력한다. 실제 회차나 AE 렌더 결과가 아니다.
- 실제 회차는 저장된 원화·확정 녹음·상태 전환·전체 효과 구간을 검토하고 실제 AE 출력의 플래시·방전·공격 궤적을 별도로 확인한다. 관리 게시/YouTube 업로드는 별개다.

## 화면과 AE의 색 일치

Wuxia 네이티브 flat 경로는 웹 PNG/SVG와 같은 비선형 채널 합성을 사용한다. AE 프로젝트의 작업 공간과 선형 합성·비트 깊이를 명시하고 설치 언어에 맞는 무손실 출력 템플릿을 선택한다. 장비에 저장된 H.264 기본 프리셋에 맡기지 않는다. 최종 MP4에는 인코딩·안티앨리어싱 오차가 있으므로 실제 디코드 프레임에서 정지 배경과 효과를 각각 비교한다. 무손실 템플릿이 없으면 명시적으로 실패하며 H.264로 조용히 대체하지 않는다.

참고 영상처럼 손으로 그린 비대칭 덩어리와 복잡한 필라멘트를 정확히 재현해야 할 때는 투명 PNG 효과 프레임을 아트 자산으로 제작하는 편이 적합하다. 한 장을 흔드는 방식이 아니라 서로 다른 방전 키 드로잉을 짧게 교체하고 잔광을 겹쳐야 한다. 이번 벡터 수정은 그 원화 질감을 달성했다는 승인이 아니며 PNG 시퀀스 자산을 새로 제작한 것도 아니다.

## 투명 PNG 방전 원화 시퀀스

`ambient_loop/v1`의 source-SHA-bound PNG 프레임 재생 경로에 선택적인 `attack_sprite` 검토 계약을 붙인다. 이 계약은 `wuxia_attack_sprite/v1`, 실제 원화 SHA, 접촉 시각, 사건·이유, 프레임 검토와 얼굴·손·무기 보호 상자를 필수로 가진다. 최대 0.6초, 반복 없음이다. 기존 벡터 전기는 선택한 검증 씬에서 제거하고 PNG만 방전으로 표시한다. 다른 씬의 수동 효과는 수정하지 않는다.

준비 도구는 이미지 생성 도구로 만든 실제 RGBA 키 드로잉을 배치·마스킹하고 시각별 불투명도를 적용해 2–16장 프레임으로 만든다. 원본 이미지 생성 알파를 유지하고, 보호 영역에 닿는 모든 알파를 제거하며 바깥쪽에만 부드러운 전이 영역을 둔다. 웹과 네이티브는 PNG 체크섬·크기와 보호 영역의 실제 알파를 검사한다. PNG 원화 자체를 Python 벡터나 임시 도형으로 대체하지 않는다.

`scripts/prepare_wuxia_attack_sprite_probe.py output/wuxia-attack-sprites-20261108`는 기존 E01_S11의 별도 검증 패키지에 점화/확장/잔광 원화 3장을 6프레임으로 준비한다. 저장한 833–1333ms 반개구간과 각 PNG duration을 `freezeWuxiaScene`이 출력 시계로 샘플링하고 AE는 똑같은 프레임 인덱스·PNG를 HOLD로 재생한다. 재생 시작/정지/탐색은 벽시계에 의존하지 않는다. 원본 회차와 확정 음성은 자동 변경하지 않는다.
