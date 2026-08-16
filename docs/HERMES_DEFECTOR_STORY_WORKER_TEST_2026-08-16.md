# Hermes Worker 탈북사연 생성 테스트 정리 - 2026-08-16

## 목적

탈북사연 카테고리 1개 데이터를 워커에서 생성하면서, Codex가 직접 호출한 경로와 사용자가 워커 시작 버튼을 눌렀을 때의 경로가 달라지지 않도록 확인했다.

이번 테스트는 대본 최종 완료 전에 중단되었으므로, 최종 결과물 1건 완성 검증이 아니라 워커 실행 경로, 중간 품질 게이트, 기획/이미지/영상 프롬프트 생성 단계의 수정 및 검증 기록이다.

## 실행 경로

워커 시작 버튼과 동일한 Dashboard API 경로로 실행했다.

```http
POST http://127.0.0.1:3002/api/autopilot/hermes/start
```

테스트 설정:

```json
{
  "settings": {
    "mode": "target_limit",
    "target_limit": 1,
    "min_buffer_per_category": 0,
    "active_categories": ["탈북사연"],
    "force_generate": true
  }
}
```

중단 요청 후 워커는 정상 정지 상태로 확인했다.

```json
{
  "is_running": false,
  "current_step": "stopped",
  "last_run_status": "stopped",
  "session_stats": {
    "generated_count": 0
  }
}
```

## 테스트 중 발생한 문제와 처리

### 1. 탈북사연 벤치마크 채널 풀이 없어 시작 실패

증상:

```text
YouTube benchmark candidate collection unavailable.
Configure benchmark_channel_ids...
```

원인:

탈북사연 카테고리에 사용할 RSS 기반 벤치마크 채널 풀이 로컬 설정에 없었다.

수정:

`data/youtube_benchmark_channels.json`에 탈북사연용 채널 ID 풀을 추가했다. 이후 로그에서 로컬 채널 풀과 Supabase 채널 풀이 병합되어 RSS 기반 후보 수집이 진행되는 것을 확인했다.

상태:

수정 완료. 시작 단계 통과 확인.

### 2. 탈북사연 씬 기획이 반복되어 품질 게이트 실패

증상:

씬 기획 QA에서 동일한 사건/감정/장면이 반복된다고 판단되어 진행이 중단되었다.

원인:

기존 반복 보정 로직이 노후금융/무협 계열에 치우쳐 있었고, 탈북사연 같은 생존 서사 카테고리에는 적절한 재구성 로직이 부족했다.

수정:

`worker/hermes_worker.py`에 생존 서사형 씬 플랜 재구성 함수를 추가했다.

핵심 동작:

- 53개 씬을 단일 생존 증언 흐름으로 재배열
- 각 씬에 고유한 사건, 감정 변화, 후킹 질문, 다음 장면 브리지를 부여
- 반복 QA 재검사 후 통과하지 못하면 완료 처리하지 않음

상태:

수정 완료. 이후 테스트에서 `Scene plan repetition QA requested survival-story rebuild` 로그가 발생했고, 기획 단계가 완료되었다.

### 3. 영상 프롬프트에 일반적 표현이 남아 품질 게이트 실패

증상:

```text
video_prompt contains generic filler for scene scene003
```

원인:

생성된 영상 프롬프트에 `camera moves` 같은 일반적이고 모호한 문구가 남았다.

수정:

영상 프롬프트 후처리에서 `camera moves`, `cameras move`를 더 구체적인 표현으로 치환하고, 최종 검증 전에 다시 정규화하도록 했다.

상태:

수정 완료. 해당 오류는 재발하지 않았다.

### 4. 마지막 영상 프롬프트 청크에서 negative guardrail 누락

증상:

```text
video_prompt missing negative motion guardrail 'no dialogue' for scene scene049
```

원인:

마지막 49-53 씬 청크에서 일부 영상 프롬프트가 `no dialogue`, `no narration`, `no subtitles` 등 필수 금지 조건을 누락했다.

수정:

영상 프롬프트 후처리 함수에서 아래 필수 guardrail이 누락되면 자동 보강하도록 했다.

- `no dialogue`
- `no narration`
- `no subtitles`
- `no captions`
- `no music`
- `no sound effects`
- `no audio`

상태:

수정 완료. 이후 미디어 프롬프트 단계가 완료되었다.

### 5. 2x2 이미지 프롬프트 기준 확인

확인 결과:

- 씬 수: 53개
- 2x2 이미지 그리드 프롬프트 수: 14개
- 마지막 그리드: 50, 51, 52, 53번 씬
- `image_grid_prompt_status`: `ready`
- `image_grid_prompt_mode`: `direct_2x2_only`

저장 파일:

```text
C:\Users\kimse\AppData\Local\AIRStudio\AIRWorker\output\hermes_results\c786cf94-6302-4c8b-bef6-df69378f34f3.json
```

UTF-8 파일 로드 기준으로 제목/주제 한글은 정상 저장되어 있었다.

```text
topic: 그날 두만강의 얼음이 부서졌다, 그리고 나는 아버지를 잃었다
upload_title: 그날 두만강의 얼음이 부서졌다, 그리고 나는 아버지를 잃었다
grid_status: ready
grid_mode: direct_2x2_only
grid_count: 14
```

상태:

수정 완료 및 중간 산출물 기준 확인 완료.

## 대본 단계 상태

대본 생성은 시작되었고, 첫 번째 생성 결과는 Story QA에서 통과하지 못했다.

QA 결과 요약:

- 점수: 72
- 판정: `revise`
- 주요 문제:
  - 초반 60초가 너무 많은 마이크로 장면으로 흩어짐
  - 아버지의 희생이라는 중심 약속이 약해짐
  - 가짜 죽음, 노트 같은 부가 플롯이 섞임
  - 같은 감정/표현이 반복됨
  - 결말의 감정적 보상이 약함

중요한 점:

이 결과는 완료 처리되지 않았고, 워커가 실패로 감지해 재시도 큐로 넘겼다. 즉, 품질이 낮은 대본을 억지로 완료시키는 문제는 이 테스트에서는 발생하지 않았다.

다만 사용자의 중단 요청으로 재시도 대본이 끝까지 완료되는지는 확인하지 않았다.

상태:

부분 확인. 품질 게이트는 작동했지만, 탈북사연 대본이 최종 통과하는지는 아직 미검증이다.

## 실행한 검증

수정 후 아래 테스트를 통과했다.

```powershell
.\venv\Scripts\python.exe -m py_compile worker\hermes_worker.py
.\venv\Scripts\python.exe -m pytest tests\test_generation_quality_gate.py tests\test_image_grid_prompts.py -q
```

결과:

```text
13 passed
```

## 현재 결론

테스트 중 발생한 모든 문제를 다 수정했다고 말할 수는 없다.

수정 완료로 볼 수 있는 것:

- 탈북사연 벤치마크 채널 풀 부재
- 탈북사연 씬 기획 반복 문제
- 영상 프롬프트의 일반적 표현 문제
- 영상 프롬프트 필수 guardrail 누락 문제
- 53씬 기준 2x2 이미지 그리드 14개 생성
- 마지막 1씬 처리 방식: 마지막 4개 씬을 다시 묶는 방식으로 50-53번 그리드 생성
- 품질 게이트가 미달 산출물을 완료 처리하지 않는 흐름

아직 완료 검증이 아닌 것:

- 탈북사연 대본 최종본이 QA를 통과하는지
- 제목부터 메타데이터까지 최종 패키지 1건이 완성되어 Supabase/유저앱 확인 화면까지 정상 반영되는지
- 워커 시작 버튼으로 사용자가 직접 눌렀을 때 장시간 실행 끝까지 완주하는지

따라서 현재 상태는 "워커 시작 경로는 정상 작동하고, 중간 품질 게이트와 2x2 프롬프트 파이프라인은 개선되어 작동 확인됨"이다. 하지만 "탈북사연 1건 최종 생성이 완전히 성공했다"라고 말할 단계는 아니다.

## 다음 권장 작업

1. 대본 생성 재시도 프롬프트를 탈북사연/생존서사 전용으로 강화한다.
2. 같은 Dashboard API 경로로 탈북사연 1건을 다시 실행한다.
3. 대본, 2x2 이미지 그리드 프롬프트, 영상 프롬프트, 메타데이터, 유저앱 확인 화면까지 최종 검증한다.
4. 최종 검증이 통과한 뒤에만 완료 처리와 배포 판단을 한다.

