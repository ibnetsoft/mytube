# Hermes 5개 카테고리 워커 점검 - 2026-08-16

## 점검 대상

- 경제
- 노후금융
- 옛날이야기
- 황혼19금
- 탈북사연

## 결론

워커 시작 버튼 경로에서 5개 카테고리 이름은 정상적으로 전달/정규화된다.

다만 "시작 버튼을 누르면 안정적으로 끝까지 생성된다"는 의미로는 아직 카테고리별 상태가 다르다.

| 카테고리 | 시작 버튼 경로 | 제목/스타일 기본값 | RSS relevance | 벤치마크 채널 풀 | 최종 생성 완주 검증 |
| --- | --- | --- | --- | --- | --- |
| 경제 | 통과 | 통과 | 보강 완료 | 로컬 11개, 원격 11개 | 미검증 |
| 노후금융 | 통과 | 통과 | 보강 완료 | 원격 4개 | 일부 테스트 이력 있음, 재완주 권장 |
| 옛날이야기 | 통과 | 통과 | 보강 완료 | 로컬 5개, 원격 5개 | 테스트 이력 있음 |
| 황혼19금 | 통과 | 통과 | 보강 완료 | 로컬 14개, 원격 14개 | 테스트 이력 있음 |
| 탈북사연 | 통과 | 통과 | 보강 완료 | 로컬 8개, 원격 13개 | 기획/이미지/영상까지 확인, 대본 최종 QA는 미완료 |

## 이번 점검에서 수정한 것

`worker/hermes_worker.py`의 RSS relevance 필터가 노후금융/무협 위주였기 때문에, 점검 대상 5개 카테고리에 대한 필터 용어를 보강했다.

보강 대상:

- 경제
- 노후금융
- 옛날이야기
- 황혼19금
- 탈북사연

이 수정은 RSS 채널 풀에서 가져온 영상 후보를 카테고리별로 걸러낼 때 엉뚱한 후보가 섞이거나, 필요한 후보가 relevance 부족으로 떨어지는 문제를 줄이기 위한 것이다.

## 추가한 회귀 테스트

파일:

```text
tests/test_hermes_category_readiness.py
```

검증 내용:

- Dashboard 시작 경로에서 들어오는 5개 카테고리명이 워커 매니저에서 정상 정규화되는지
- 각 카테고리의 제목 스타일과 fallback 제목이 존재하는지
- fallback 제목이 제목 QA를 통과하는지
- 5개 카테고리 모두 RSS relevance 용어를 갖는지

## 실행한 테스트

```powershell
.\venv\Scripts\python.exe -m py_compile worker\hermes_worker.py worker\hermes_autopilot.py
.\venv\Scripts\python.exe -m pytest tests\test_hermes_category_readiness.py tests\test_generation_quality_gate.py tests\test_image_grid_prompts.py -q
```

결과:

```text
16 passed
```

## 시작 버튼 경로 점검

워커 대시보드의 카테고리별 시작 버튼은 아래 경로를 호출한다.

```http
POST /api/autopilot/hermes/start
```

전달 설정은 카테고리별 시작 시 다음 형태다.

```json
{
  "settings": {
    "mode": "target_limit",
    "target_limit": 1,
    "min_buffer_per_category": 1,
    "active_categories": ["카테고리명"],
    "force_generate": true
  }
}
```

공통 시작 버튼도 동일한 `/api/autopilot/hermes/start` 경로를 사용한다. 서버는 이 요청을 받으면 `hermes_worker` 프로세스를 시작하고, 같은 설정으로 autopilot loop를 실행한다.

현재 상태 조회 결과 워커는 중단 상태다.

```json
{
  "is_running": false,
  "current_step": "stopped",
  "last_run_status": "stopped",
  "last_error": "",
  "session_stats": {
    "generated_count": 0
  }
}
```

## 벤치마크 채널 풀 상태

현재 확인된 채널 풀:

```text
경제: local 11, remote 11, merged 11
노후금융: local 0, remote 4, merged 4
옛날이야기: local 5, remote 5, merged 5
황혼19금: local 14, remote 14, merged 14
탈북사연: local 8, remote 13, merged 13
```

의미:

- 경제, 황혼19금, 옛날이야기, 탈북사연은 RSS 기반 벤치마크 풀로 시작 가능성이 높다.
- 노후금융은 원격 4개가 있으나 기본 목표 8개보다 적어서 자동 채널 발견이 추가로 작동할 수 있다.

자동 채널 발견은 시작 실패를 줄이는 장점이 있지만, 최초 발견 시 YouTube `search.list` quota를 사용할 수 있다. 현재 경제/황혼19금은 로컬과 Supabase 풀을 보강했으므로, 이 두 카테고리는 기본 목표 8개를 넘겨 자동 발견 의존도가 낮아졌다.

## 카테고리별 판단

### 경제

공통 품질게이트, 2x2 이미지 그리드, 영상 guardrail 보정은 적용된다.

제목/스타일/fallback 제목도 정상이다.

로컬 11개, Supabase 11개 채널 풀이 있어 RSS 기반으로 벤치마크를 시작할 수 있다.

### 노후금융

공통 품질게이트와 금융/경제 계열 보정이 적용된다.

원격 채널 풀이 4개 있어 경제보다는 낫지만, 기본 목표 8개보다 적다. 따라서 자동 발견이 추가로 작동할 수 있다.

### 옛날이야기

로컬/원격 채널 풀이 있고, 2x2 이미지 그리드 및 마지막 53씬 처리 관련 테스트 이력이 있다.

시작 버튼 경로로 돌릴 수 있는 상태로 판단한다.

### 황혼19금

공통 품질게이트와 story 계열 보정이 적용된다.

로컬 14개, Supabase 14개 채널 풀이 있어 RSS 기반으로 벤치마크를 시작할 수 있다.

### 탈북사연

로컬 8개, 원격 13개 채널 풀이 있어 RSS 기반 벤치마크 단계는 이전보다 안정적이다.

생존서사형 씬 기획 반복 보정, 2x2 이미지 그리드, 영상 프롬프트 guardrail 보강까지 확인했다.

단, 직전 테스트는 대본 최종 완료 전에 중단했기 때문에 대본 QA 최종 통과는 아직 미검증이다.

## 최종 답변 기준

현재 "워커 시작 버튼을 눌러도 되는가"에 대한 답은 다음과 같다.

- 옛날이야기: 가능
- 탈북사연: 가능하나 대본 QA 최종 통과는 추가 확인 필요
- 노후금융: 가능하나 채널 풀 보강 권장
- 경제: 가능
- 황혼19금: 가능

따라서 5개 모두 코드 경로와 공통 품질게이트는 적용되어 있다. 경제/황혼19금은 이번 보강으로 벤치마크 채널 풀 부족 문제도 해소했다. 노후금융은 여전히 원격 4개라 추가 보강 여지가 있다.
