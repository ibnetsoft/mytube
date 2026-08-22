# Hermes Worker 생성 오류 정리 - 2026-08-22

이 문서는 2026-08-22 로컬 AIR Worker/Hermes 자동 생성 중 실제 대시보드에서 확인된 오류와 수정 내용을 정리한다. 핵심 결론은 대부분이 "생성 엔진이 완전히 멈춘 오류"가 아니라, 재시작/이어하기/대시보드 집계가 실제 파이프라인 상태를 정확히 반영하지 못해 반복 오류처럼 보인 문제였다는 점이다.

## 최종 상태

- Manager, Local API, Hermes Worker, Render Worker, Drive Worker 생명주기 정리 완료.
- Hermes 자동 생성은 새 작업에서 실제 `web_research` 잡을 거친 뒤 다음 단계로 진행하도록 수정.
- 과거 레거시 작업은 이미 downstream 산출물이 있으면 벤치마크 실패가 전체 상태를 덮어쓰지 않도록 수정.
- `publish_metadata_generate`까지 완료된 작업은 누락된 이전 단계 표시가 있어도 `제작 완료`로 처리.
- 서버 재시작 모달은 `/api/status` 응답 지연 시에도 멈추지 않도록 timeout + cache-busting reload 적용.

## 오류별 정리

| 화면 오류/증상 | 실제 원인 | 수정 내용 | 관련 커밋 |
|---|---|---|---|
| `cannot access free variable 'image_style' where it is not associated with a value in enclosing scope` | Hermes 대본/기획 흐름에서 이미지 스타일 변수 초기화 순서가 어긋나 일부 카테고리에서 closure scope 참조가 실패했다. | 이미지 스타일 선택/전달 흐름을 명확히 하고 재시작 후 이어하기 가능하게 정리. | `93bc00c8`, 후속 관련 수정 |
| `name 'finance_plan_context' is not defined` | 특정 카테고리 전용 플랜 컨텍스트 변수가 공통 파이프라인에서 정의 없이 참조됐다. | 카테고리별 컨텍스트 분기와 fallback을 정리해 공통 8개 카테고리에서 동일 흐름을 타도록 보정. | 후속 관련 수정 |
| `Hermes was restarted after fixing finance_plan_context; resume this job to run with patched code.` | 코드 수정 후 기존 실패 잡은 자동으로 새 코드에서 재실행되지 않아 안내용 오류로 남았다. | 이어하기 로직을 강화해 완료 산출물 기준으로 다음 단계 잡을 재제출할 수 있게 수정. | `93bc00c8` |
| `publish_metadata quality gate failed: script_quality_report not passing: verdict=revise, score=62` | 대본 품질 게이트가 `revise` 판정을 받아 설명/태그 발행을 막았다. | 품질 리포트 해석과 레거시 완료 상태 표시를 분리. 실제 설명/태그 완료 시에는 최종 완료로 처리. | `2c0d5b44` |
| `재시작 실패: 이미 설명·태그 단계까지 완료된 작업입니다.` | 이미 최종 단계까지 완료된 작업에 이어하기를 눌러 resume API가 거부했다. UI는 이를 오류처럼 보여줬다. | `publish_metadata_generate` 완료가 있으면 전체 파이프라인을 `제작 완료`로 표시하도록 변경. | `2c0d5b44` |
| 대시보드 75%에서 `이어하기`가 안 됨 | 일부 작업은 `script_generate`까지 완료됐지만 과거 `topic_benchmark_analyze` 실패가 전체 파이프라인 오류를 덮어썼다. | 벤치마크 실패와 downstream 진행률을 분리. 기획/대본/메타데이터 중 하나라도 완료되면 벤치마크 실패가 전체 오류 배지를 덮지 않도록 변경. | `9ee26468` |
| `YouTube benchmark candidate collection unavailable; benchmark cannot continue: YouTube search fallback is disabled...` | YouTube benchmark 후보 수집 설정이 없었다. `benchmark_channel_ids` 또는 `YOUTUBE_BENCHMARK_CHANNELS_JSON`이 없고 검색 fallback도 꺼져 있어 벤치마크 잡이 실패했다. | 새 작업은 캐시 벤치마크로 웹자료조사를 대체하지 않고 반드시 실제 `web_research` 잡을 생성하도록 수정. 과거 작업은 downstream 산출물 기준으로 표시 보정. | `35aaca0c`, `9ee26468` |
| 웹자료조사 없이 다음 단계가 진행된 것처럼 보임 | 캐시된 benchmark 결과를 `research_bundle`처럼 만들어 `web_research` 잡 없이 기획 단계로 넘기는 우회 경로가 있었다. | 캐시 benchmark는 seed로만 사용하고, 실제 `web_research` 완료 후에만 `script_plan_generate`로 진행하도록 수정. | `35aaca0c` |
| 대시보드에서는 완료인데 Hermes 자동 생성 페이지에서는 실패/동작 중으로 표시 | dashboard와 Hermes autopilot page가 서로 다른 상태 소스를 보고 있었다. 완료된 job 결과와 autopilot 내부 상태가 동기화되지 않았다. | 완료 job 기준으로 autopilot page와 dashboard 표시를 동기화. 중복 autopilot loop도 차단. | `ce85684e`, `bfcf6206`, `cdae5fb3` |
| 주제 생성 시작 후 대시보드에는 아무 작업도 안 뜸 | Autopilot 내부 단계는 진행 중이지만 아직 job_store에 실제 단계 잡이 생기기 전이라 dashboard 최근 파이프라인에 표시할 row가 없었다. | `/api/jobs`가 실행 중인 autopilot 내부 단계를 virtual job으로 노출하도록 수정. | `c78a1e4a` |
| 주제 생성 페이지는 동작 중인데 대시보드는 완료 또는 반대로 표시 | Hermes Worker 프로세스 상태와 Autopilot manager 내부 상태가 따로 놀았다. | dashboard process card가 visible pipeline row와 autopilot status를 같이 보도록 동기화. | `cdae5fb3`, `ce85684e` |
| `Manager 오프라인` 배지가 떠서 자동 생성이 불안정해 보임 | dashboard는 살아 있지만 Manager heartbeat 파일이 오래되어 dashboard와 Manager 생명주기가 어긋난 상태였다. | status endpoint에서 Manager recovery를 시도하고, 재시작 helper가 Manager를 포함한 전체 프로세스를 재기동하도록 보강. | `ade8ea9b` 및 관련 수정 |
| 서버 완전 재시작 버튼을 눌러도 변화가 없음 | helper가 실제 실행 커맨드라인(`dashboard_app:app`, `air_worker_entry.py --role ...`) 일부를 못 잡아 이전 프로세스가 남았다. | 현재 프로젝트 경로 + 역할명 기준으로 dashboard/manager/worker/local_api 프로세스를 탐지해 종료하도록 수정. | `ade8ea9b` |
| 재시작 모달에서 `45초` 대기 상태로 멈춤 | `/api/status` polling 요청이 오래 물리면 모달이 reload까지 가지 못했다. | 각 polling 요청에 `AbortController` 2.5초 timeout 적용, 준비 확인 또는 timeout 시 `?restarted=<timestamp>`로 cache-busting reload. | `8f627354` |

## 현재 파이프라인 판정 규칙

1. 새 Hermes 자동 생성은 `topic_benchmark_analyze` 이후 반드시 `web_research`를 실행한다.
2. `web_research`가 없으면 1단계 `웹 자료조사`는 완료로 위장하지 않는다.
3. 다만 과거 작업에서 이미 `script_plan_generate`, `script_generate`, `publish_metadata_generate` 중 downstream 단계가 완료된 경우, 과거 `topic_benchmark_analyze` 실패는 전체 파이프라인 오류를 덮어쓰지 않는다.
4. `publish_metadata_generate`가 완료된 작업은 최종 산출물이 있으므로 전체 파이프라인을 `제작 완료`로 처리한다.
5. `script_generate`까지만 완료된 작업은 `이어 가능`으로 표시되고, 이어하기 시 `publish_metadata_generate` 잡을 제출한다.

## 운영자가 볼 때의 해석

- `오류 + 25%`: 기획 이전 단계에서 실제로 멈춘 상태일 가능성이 높다.
- `이어 가능 2/4`: 기획까지 완료됐고 대본 생성부터 이어갈 수 있다.
- `이어 가능 3/4`: 대본까지 완료됐고 설명/태그 생성부터 이어갈 수 있다.
- `제작 완료 100%`: 설명/태그까지 생성된 상태다. 과거 benchmark 실패 로그가 남아 있어도 최종 산출물은 완료로 본다.

## 남은 설정 주의점

YouTube benchmark 실패 자체를 줄이려면 다음 중 하나가 필요하다.

- 카테고리별 `benchmark_channel_ids` 설정.
- `YOUTUBE_BENCHMARK_CHANNELS_JSON` 환경변수 설정.
- YouTube search fallback을 명시적으로 활성화하는 정책 결정.

현재 수정은 이 설정 부재를 숨기지 않는다. 다만 이미 downstream 단계가 성공한 파이프라인은 대시보드에서 불필요하게 실패로 보이지 않게 한다.

## 검증된 테스트

반복 수정마다 아래 테스트를 기준으로 확인했다.

```powershell
python -m py_compile worker\dashboard_app.py
python -m py_compile worker\hermes_autopilot.py worker\dashboard_app.py
python -m pytest tests\test_dashboard_pipeline_ui.py tests\test_worker_dashboard_offline_harness.py -q
```

주요 테스트 커버리지:

- 실패 파이프라인이 오류 이유와 이어하기 버튼을 표시하는지.
- 최종 메타데이터 완료 작업이 전체 완료로 표시되는지.
- downstream 생성 단계가 있으면 benchmark 실패가 전체 상태를 덮지 않는지.
- cached benchmark가 실제 `web_research`를 대체하지 않는지.
- 재시작 모달이 Manager readiness 확인 후 reload하며 polling hang에 빠지지 않는지.

## 관련 커밋 목록

- `93bc00c8` Fix Hermes resume recovery for long scripts
- `ce85684e` Sync Hermes autopilot page with completed jobs
- `cdae5fb3` Sync Hermes running state across dashboard processes
- `bfcf6206` Prevent duplicate Hermes autopilot loops
- `c78a1e4a` Show Hermes autopilot internal progress in jobs
- `59417f9e` Fix Hermes fallback pipeline status
- `35aaca0c` Require Hermes web research before planning
- `ade8ea9b` Make worker server restart wait for readiness
- `2c0d5b44` Treat completed metadata as finished Hermes pipeline
- `9ee26468` Show downstream Hermes progress despite benchmark failure
- `8f627354` Prevent restart modal from hanging

