# 이미지 생성 실패·거절 폴백

캐릭터 → 씬 이미지 → 썸네일 배경에 공통 적용한다. `worker/image_recovery.py`는 내장 이미지 도구의 작업 상태를 기록하는 실행 제어기이며, 자체적으로 이미지 도구/API를 호출하지 않는다. CoWork 에이전트가 내장 도구를 호출하고 결과를 기록한다. 다른 카테고리나 영상 길이도 동일한 규칙을 사용한다.

## 분기와 한도

| 결과 | 다음 행동 |
|---|---|
| 생성 성공 | 실제 파일 검사 → 시각 검수 → ready. 생성만으로 DB 저장 완료가 아님 |
| 명확한 일시 오류, 결과 없음 | 같은 요청 재시도: 30초·120초 대기, 최초 포함 최대3회 |
| 패널 순서·인물·구도 불량 | 시각 검수 불합격 기록. 그리드는 원래 씬별 프롬프트를 이용해 개별 이미지로 분리 가능 |
| 안전 거절 | safety_review. 같은 요청 재시도·자동 분할·자동 문구 수정·모델 교체 금지 |
| 원인 불명·응답 유실·타임아웃 | needs_review. 생성된 파일 유무부터 확인; 자동 재호출 금지 |
| 사용량 한도·도구 없음 | quota_wait / unavailable. 리셋·추가 결제·API 전환하지 않음. 실제 해결 근거가 있을 때만 재개 |

대안 분기는 원본 작업당 한 번, 각 하위 씬도 부모의 시도 횟수를 상속해 최대3회 예산을 넘지 않는다. 분리된 씬에서 다시 대안 분기를 만들어 무한 반복하지 않는다. 결과에 safety/content_filter 신호가 있으면 transient로 잘못 입력해도 안전 검토 상태가 우선한다. 그리드 거절로 어느 씬이 문제인지 또는 왜 거절됐는지 단정하지 않는다.

안전 거절 뒤에는 검토자가 **허용되는 별도의 연출안인지** 판단해야 한다. 단어만 감추거나 캐릭터 나이 등을 조작해서 같은 거절 내용을 통과시키는 것은 금지한다. 대본의 핵심 사건·인물·나이·시대·카테고리 스타일을 보존하고, 필요하면 사건에 맞는 비폭력적인 행동이나 핵심 사물을 표현한다. 변경된 연출안은 사용자에게 보여 승인을 기록한 뒤에만 큐에 넣는다. 허용되지 않는 내용이면 stop으로 종료한다. 안전 검토 필드는 승인 기록이지 코드가 정책 적합성을 자동 판정했다는 뜻이 아니다.

## 씬 작업

새 `cowork_scene_assets.py export`는 `manifest.recovery.json`을 함께 만든다. 원본 대본과 씬별 프롬프트, 캐릭터 참조는 manifest의 `scene_specs`와 `character_references`에 보존된다. 같은 경로 재export는 거절해 성공 파일/실패 이력을 잃지 않는다. 새 대본 버전은 새 경로를 사용한다.

```powershell
python worker/cowork_scene_assets.py export --topic-id <ID> --out cowork_batches/<ID>/v2/manifest.json
python worker/image_recovery.py status --manifest cowork_batches/<ID>/v2/manifest.json
python worker/image_recovery.py event --manifest cowork_batches/<ID>/v2/manifest.json --event event.json
```

`event.json`은 한 번에 이벤트 하나다. CoWork는 도구 호출 **전** start를 기록하고, 다음 상태에서 runnable 작업만 호출한다.

```json
{"action":"start","job_id":"grid-006"}
```

내장 도구 성공 후 실제 경로를 기록한다. 프로젝트 산출물은 작업 폴더에 복사하고 원본은 보존한다.

```json
{"action":"result","job_id":"grid-006","outcome":"generated","image_file":"D:/Projects/example/raw/grid-006.png"}
```

픽셀을 실제로 확인한 뒤에만 검수 통과를 기록한다. 캐릭터·스타일·시대·행동·패널 순서·문자·해부학을 확인한다.

```json
{"action":"accept","job_id":"grid-006","visual_review":"4개 패널의 지정 장면·인물·나이·의상·순서와 문자 없음 확인"}
```

불량 이미지가 나왔으면 `reject_quality`, 이후 `split_quality` 이벤트를 사용한다. 기존 scene_specs가 없으면 임의로 프롬프트를 만들지 않고 중단한다. 각 자식 작업은 grid-006-alt-1처럼 별도 ID를 받으며 참조 이미지를 그대로 유지한다. 실제 생성 방식은 단일16:9로 바뀐다.

거절 기록 예시:

```json
{"action":"result","job_id":"grid-006","outcome":"safety","code":"output_safety","reason":"구체적 이유 미제공","request_id":"도구가 반환한 요청 ID"}
```

대안 검토 이벤트 형식(원본이 4씬이면 proposals에 정확히 해당4씬을 모두 넣어야 함):

```json
{
  "action":"review", "job_id":"grid-006", "decision":"alternative",
  "review":{
    "reviewer":"검토자",
    "reason":"실제 대본을 근거로 검토한 새로운 연출 설명",
    "source_fidelity":"유지되는 핵심 사건·인물·소품",
    "character_age_style_preserved":"원래 나이·캐릭터 DNA·시대·스타일 확인",
    "safety_assessment":"allowed_alternative",
    "user_approval":"해당 연출안을 승인한 사용자 메시지 또는 기록"
  },
  "proposals":[
    {"scene_numbers":[21],"prompt":"검토·승인된 씬21 단일 이미지 프롬프트"},
    {"scene_numbers":[22],"prompt":"검토·승인된 씬22 단일 이미지 프롬프트"},
    {"scene_numbers":[23],"prompt":"검토·승인된 씬23 단일 이미지 프롬프트"},
    {"scene_numbers":[24],"prompt":"검토·승인된 씬24 단일 이미지 프롬프트"}
  ]
}
```

이력에는 원본/대안 프롬프트·이유·검토·승인·요청ID·시도 횟수·파일 해시가 남는다. 키/토큰/전체 오류 덤프는 기록하지 않는다. 상태 변경은 단일 작성자 잠금과 원자적 파일 교체를 사용한다. 종료된 프로세스가 running이나 lock을 남겼다면 실제 도구 실행·파일 존재부터 확인한다. 자동 잠금 삭제나 무조건 재시작을 하지 않는다.

## 크롭·저장·재개

모든 활성 이미지가 ready일 때 기존 crop → publish를 실행한다. crop은 성공한 그리드와 단일 이미지를 혼합 처리한다. 단일 이미지를 다시4등분하지 않는다. 중첩 마지막 그리드의 씬은 최초 매핑을 유지한다.

- 이미지 검수 후 파일 해시가 바뀌면 중단.
- 크롭 결과는 1920×1080. 재실행 시 픽셀이 같은 기존 파일은 건너뛰고, 다른 파일은 덮어쓰지 않고 중단.
- crop-receipt.json은 정확한 씬별 파일 해시와 원본 manifest 버전을 기록.
- publish는 전체 완료·원본 해시·크롭 파일 해시를 확인한 후에만 저장 경로 진입.
- 미완료 씬은 다른 이미지로 채우지 않는다. 생성 성공 수와 실제 저장/재조회 검증 수를 구분해 보고한다.
- 부분 저장이 필요한 운영 리페어는 별도의 범위 한정 저장 절차를 이용하고 전체 ready로 보고하지 않는다. 이 큐는 자동으로 기존 사용자 프로젝트나 DB를 변경하지 않는다.
- 이미 진행 중이던 옛 manifest는 `init`으로 명시적으로 도입할 수 있지만 기존 생성/검수 결과는 실제 파일 확인 후 이력을 등록해야 한다. 거절을 pending으로 초기화해 재시도하지 않는다.

## 캐릭터와 썸네일

`NativeCodexImageGenerator`는 캐릭터 작업 폴더의 image-job.recovery.json을 자동으로 사용한다. 거절/원인불명은 재실행해도 다시 생성하지 않는다. 검토된 대안 작업이 있으면 그 프롬프트를 사용하며 성공 파일은 해시 검증 후 재사용한다. 캐릭터 실패 시 같은 이야기에 종속된 씬 생성은 중단하지만 다른 이야기 작업까지 폐기하지 않는다.

썸네일 export도 recovery 상태를 만든다. 같은 start/result/accept 흐름을 거친 뒤:

```powershell
python worker/cowork_thumbnail_asset.py publish --topic-id <ID> --manifest cowork_batches/<ID>/thumbnail.json --image <검수된_파일> --create-bucket
```

썸네일은 텍스트 없는 배경만 생성하며, 편집 문구와 사용자 최종 저장 계약은 유지한다. 프로그램 내부의 기존 publish 호출은 하위 호환을 유지하지만, CoWork CLI는 manifest를 필수로 요구한다.

## 검증 범위

## 어린이·청소년 등장 장면 (2026-09-16)

- 실제 이야기 나이와 시대·복장·캐릭터 정체성을 유지한다. 회상에는 해당 나이의 검수된 참조 이미지를 사용한다.
- 연령에 적합한 비성적·비착취적 묘사를 사용하고, 극적 효과를 위해 아동의 고통·부상·피해를 임의로 추가하지 않는다.
- 이야기 의미를 유지할 수 있다면 시선, 거리, 배경으로 감정을 간접적으로 표현한다. 중대한 연출 변경은 사용자 승인 후 적용하고 원본 프롬프트를 보존한다.
- 나이를 숨기거나 성인으로 바꾸는 등 안전장치를 우회하지 않는다. 거절 시 자동 재시도 대신 원문 응답과 검토·승인 이력을 기록한다.
- 일반적인 경고만으로 정확한 거절 원인을 단정하지 않는다. 어린이의 모든 슬픔 표현이 금지된다는 뜻도 아니다.
- 3292의 24씬은 사용자의 변경 요청에 따라 12세 순덕이 편안히 앉아 창밖을 바라보고 38세 어머니가 떨어져 앉는 일상적 연출로 수정했다. 대본은 유지했다.
- 실행 지침은 `worker/child_image_guidance.py`에서 캐릭터 참조, 씬 프롬프트, 썸네일 작성 단계에 전달한다.

`tests/test_image_recovery.py`는 거절/오류 분리, 안전 신호 우선, 재시도 한도·대기, 재시작, 대안 승인, 씬 분할·매핑, 크롭 재개, 파일 변조 및 미완료 publish 차단을 검증한다. 실제 거절을 일부러 유발하는 실험이나 운영 DB 테스트는 하지 않는다.
