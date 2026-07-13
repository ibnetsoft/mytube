# AIR Worker — 원격 렌더링 E2E QA 결과 (AIR-0227C Stage 9/14)

- 상태: **로컬 모의 중앙 서버 기준 실측(아래 본문) + [AIR-0227D-STAGING-UNBLOCK 최종] 실제 프로덕션 Supabase/실제 배포된 Vercel 프리뷰(PR #85) 기준 HTTP 레벨 실측까지 완료 — register/heartbeat/claim/renew/progress/complete 전체 라운드트립, 인증 실패(401)/Idempotency-Key 누락(400) 케이스 포함(worknote/AIR-0227D-STAGING-UNBLOCK.md §6). 실 Google Drive 업로드/다운로드 E2E만 여전히 미검증(테스트 자격증명 없음). 아래 본문의 상세 시나리오(lease 만료/재할당, 네트워크 장애, idempotency)는 로컬 모의 서버 기준이며 프로토콜 동작 자체는 경로 변경과 무관하게 유효.**
- 관련 문서: [LEASE_PROTOCOL](./AIR_WORKER_LEASE_PROTOCOL.md), [AUTH](./AIR_WORKER_AUTH.md)

## 0. 왜 "실제 원격"이 아니라 로컬 모의 서버인가

§AUTH.md §0에 상세 - 운영 Supabase/Vercel을 건드리지 않기 위한 의도적 선택. 아래 결과는
전부 `worker/dev_central_server`(실제 HTTP round-trip, 실제 SQLite, 실제 네트워크 단절
시뮬레이션)를 상대로 한 것이며, `central_client.py`는 이 서버와 실제 auth-web을 구분하지
않으므로 프로토콜 차원의 검증으로서는 유효하다.

## 1. 정상 플로우 실측

```
1. worker/dev_central_server/run.py 기동 (포트 8799)
2. /_test/seed-job로 render_video 작업 1건 생성
3. Manager(AIRWORKER_CENTRAL_SERVER_URL=http://127.0.0.1:8799,
  AIRWORKER_TOKEN=test-worker-token-A) 기동
4. Render Worker가 0.4초 만에 자동 claim
5. PREPARING -> RENDERING (진행률 50%/100% 보고 확인) -> UPLOADING -> COMPLETED
6. 로컬 job_store: source=central_server, lease_id/worker_instance_id/remote_job_id 전부 채워짐,
  remote_ack_status=acked
7. 중앙 서버(모의) 쪽 기록: status=completed, output_ref=로컬 delivered 경로와 정확히 일치
8. 실제 출력 검증: ffprobe로 h264/aac, 1280x720, 24fps, 4.00초 확인
```

## 2. lease 갱신 실측

~20초 렌더링 동안 3초 간격으로 6회 `renew-lease` 호출 성공 로그 확인 (8초 TTL을 훨씬
넘겨서도 살아있었음 - 갱신 메커니즘이 실제로 lease를 붙잡아 두고 있다는 증거).

## 3. lease 만료 + 재할당 실측

1. 작업 1건 seed, 클레임 확인(lease_id A)
2. Render Worker 강제 종료(크래시 시뮬레이션) - 갱신 중단
3. Manager가 즉시 감지, 새 Render Worker 자동 기동(bounded auto-restart)
4. 원래 lease의 TTL(8초)이 지난 뒤 새 Render Worker의 다음 claim 시도가 만료된 lease를
   스윕하고 같은 작업을 새 lease(lease_id B, `attempt_number: 2`)로 재할당
5. 재할당된 렌더링이 정상 완료

**stale lease 완료 거부 실측**: 크래시한 워커의 옛 lease_id A로 수동 `/complete` 호출 →
`409 job is not in leased state (status=completed)` - 이미 새 lease로 완료된 뒤라 정확히
거부됨.

## 4. idempotency 실측

같은 `Idempotency-Key`로 `/complete`를 2번 호출: 첫 응답은 `idempotent_replay: false`,
두 번째는 `idempotent_replay: true`이며 **두 번째 호출의 다른 output_ref 값은 무시되고
첫 번째 값이 그대로 유지됨** - 재전송이 실제로 안전함을 확인.

## 5. 네트워크 장애 실측 (제일 중요한 시나리오)

1. 작업 렌더링 도중 중앙 서버 프로세스를 강제 종료(포트 소유 PID로 정밀 타겟팅)
2. lease 갱신 5회 재시도(지수 백오프) 후 실패 - **논-fatal, 렌더링 자체는 계속 진행**
3. 렌더링은 정상 완료, 로컬 COMPLETED 확정, output.mp4 실제 생성
4. `/complete` 보고도 5회 재시도 후 실패 → `remote_ack_status=pending`으로 저장, 로컬 상태는
   그대로 최종 확정(렌더 결과 손실 없음)
5. Render Worker 프로세스는 **크래시하지 않고** idle로 복귀 (restart_count 불변으로 확인)
6. 중앙 서버 재기동 → 다음 루프 반복에서 `_flush_pending_remote_acks()`가 자동으로
   재전송 시도 (다만 lease TTL을 이미 넘긴 경우의 후속 동작은 §LEASE_PROTOCOL §6 "알려진
   제한사항" 참고 - 완전히 무결하지는 않음, 실측으로 원인까지 확인)

### 이 시나리오에서 실제로 발견하고 고친 버그

1. **프로세스 크래시**: 첫 실측 시 이 시나리오가 그대로 Render Worker를 죽였다(409를 못
   받아내는 예외 처리 버그) - 코드 수정 후 동일 시나리오 재실행으로 크래시 없음을 재확인.
2. **무한 재시도 vs 영구 포기 구분 없음**: lease가 이미 만료/재할당된 뒤의 완료 보고는
   영원히 'pending'으로 남아 매 루프 재시도되고 있었다 - `LeaseConflict`(409) 전용 처리를
   추가해 'abandoned'로 전환, 유닛 테스트로 크래시 없음과 상태 전이를 재확인.

## 6. 인증 오류 실측

`AuthError`(401/403)는 `claim`/`report_progress`/`renew_lease`/`_report_remote_outcome`
전부에서 **재시도 없이 즉시 로그하고 다음 틱으로 넘어가는지** 코드 경로로 확인(전용 except
분기 존재, `_request()`가 401/403을 만나면 백오프 루프에 들어가지 않고 즉시 raise) -
실제 잘못된 토큰으로 별도 재현은 하지 않았으나(Stage 3의 Local API 토큰 테스트와 동일한
`hmac.compare_digest` 기반 검증 로직을 central_client 쪽 서버가 그대로 사용하므로 위험도
낮음), 코드 리뷰로 대체.

## 7. 우선순위/동시성 (Stage 12에서 재확인)

10개 스레드(AIR Worker 토큰 5개 + 레거시 토큰 5개)가 동시에 같은 작업 1건을 claim
시도 → 정확히 1명만 성공. §JOB_RECOVERY의 로컬 SQLite `BEGIN IMMEDIATE` 패턴과 동일한
원자성 보장이 중앙 서버(모의) 쪽에도 적용됨을 실측 확인.

## 8. 실행하지 않은 항목 (정직하게 명시)

- 실제 auth-web/Supabase 대상 E2E (§0에서 설명한 의도적 범위 결정)
- 실제 Google Drive 다운로드/업로드 E2E (§DRIVE_ADAPTER.md - 테스트 자격증명 없음)
- 서버 500 응답에 대한 백오프 실측(코드 경로는 존재 - `_request()`가 5xx를 5xx 전용 분기로
  재시도 - 하지만 이번 세션에서 5xx를 실제로 흉내내는 별도 테스트는 하지 않음, 네트워크
  단절(§5)과 로직상 같은 재시도 경로를 타므로 위험도는 낮게 평가)
