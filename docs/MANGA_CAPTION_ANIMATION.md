# 선택 장면 AE 자막 애니메이션

일반 자막은 기존 편집 경로를 따른다. 아래 연출 자막은 명시적으로 선택한 레이어드 PSD AE 장면에만 추가한다. 그림에는 글자를 굽지 않는다.

## 프리셋

- `punctuation_pop`: 짧은 문구와 붉은 `!!!`를 순간 확대한다.
- `brush_phrase`: 흰 문구 안의 선택한 구절을 붉게 강조한다.
- `headline_punch`: 굵은 흰 문구 안의 강조 구절을 노랗게 확대한다.
- `floating_dialogue`: 인물 옆 붉은 대사를 짧게 밀어 넣는다.

## 음성 연결

최종 승인된 **장면 상대 시간**의 단어 목록과 실제 편집에 쓸 음성 파일이 확정된 뒤 `worker.manga_caption_animation.prepare_caption_animation`을 호출한다. 예:

```python
scene["ae_template"] = "dialogue_closeup"
scene["ae_caption_animation"] = prepare_caption_animation(
    audio_path=approved_scene_voice,
    words=[
        {"text": "그", "start_seconds": 0.30, "end_seconds": 0.52},
        {"text": "순간", "start_seconds": 0.55, "end_seconds": 0.91},
    ],
    captions=[
        {"preset": "punctuation_pop", "text": "그 순간", "accent_text": "순간", "position": [0.72, 0.53]},
    ],
    duration=4,
)
```

문구는 연속된 단어와 정확히 한 번 일치해야 한다. 여러 번 반복된 문구, 누락된 발화, 중복·역순 단어 시점은 계획 단계에서 거부한다. 강조 구절의 등장 시점도 해당 단어의 시작 시점에서 계산한다. `position`은 0~1 정규화 화면 좌표다. 한 장면에 최대 네 문구를 선택할 수 있다.

계획과 AE 렌더 전 검수는 승인 음성의 SHA-256, 단어 시점, 프리셋, 화면 안전 영역을 다시 확인한다. 음성이 교체되면 시점을 재승인해야 한다. 렌더 후에는 문구 위치의 전후 프레임 차이를 확인하며, 실제 한글 글꼴·맞춤법·가림·음성과의 시각적 일치는 사람이 재생하며 최종 검수한다. 일반 자막과 연출 자막이 동시에 겹치는 구간도 편집에서 확인한다.

## 효과음 연동 의성어

음성에 나오지 않는 `쿵!`, `슉—` 같은 문구는 별도 `ae_sfx_text_animation`으로 지정한다. `sfx_events`의 장면 상대 시작·끝 시간과 ID가 효과음 타임라인을 나타내고, 각 텍스트 큐가 그 ID를 참조한다. 음성 전사/단어 타이밍은 사용하지 않는다.

```python
from manga_caption_animation import prepare_sfx_text_animation

scene["ae_template"] = "ink_splat_impact"
scene["ae_sfx_text_animation"] = prepare_sfx_text_animation(
    sfx_events=[{"id": "stone-hit", "label": "돌 충돌", "start_seconds": 1.24, "end_seconds": 1.62}],
    cues=[{"sfx_event_id": "stone-hit", "text": "쿵!", "preset": "sfx_impact",
           "offset_seconds": 0, "hold_seconds": 0.72, "position": [0.56, 0.44]}],
    duration=4,
)
```

지원 프리셋은 충돌 확대(`sfx_impact`), 옆으로 진입(`sfx_whoosh`), 노란 핵심어 팝(`sfx_emphasis`)이다. 프레임 안 시간, 이벤트 ID, 위치, 표시 길이를 AE 계획에서 재검증한다. 효과음 편집으로 이벤트 시점이 달라지면 큐를 다시 준비해야 하며, 최종 믹스와 영상 재생으로 싱크를 검수한다. 한 장면은 최대 네 개의 SFX 텍스트를 사용한다.
