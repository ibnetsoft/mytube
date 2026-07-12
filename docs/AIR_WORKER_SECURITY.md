# AIR Worker — 보안 설계

- 상태: **§1(Worker Token)·§2(Local API) 구현 및 실측 완료(AIR-0227C) / §3(중앙 서버 실연동) 여전히 설계만**
- 관련 문서: [ARCHITECTURE](./AIR_WORKER_ARCHITECTURE.md), [JOB_PROTOCOL](./AIR_WORKER_JOB_PROTOCOL.md), [AUTH](./AIR_WORKER_AUTH.md), [LOCAL_API_SECURITY](./AIR_WORKER_LOCAL_API_SECURITY.md)

> **AIR-0227C 업데이트**: §2의 "로컬 전용 토큰... 후속 단계에서 검토"는 이제 후속이 아니라
> 구현·실측 완료됐다 - 상세는 [LOCAL_API_SECURITY.md](./AIR_WORKER_LOCAL_API_SECURITY.md).
> §1의 Worker Token 형태 제안(HMAC)도 실제로 구현·검증됐다 - 상세는
> [AUTH.md](./AIR_WORKER_AUTH.md). §5의 잔여 위험 1번(Local API 무인증)은 이번 Task로
> 해소됐다(아래 §5 갱신 참고). §3(중앙 서버 실연동)은 로컬 모의 서버로 프로토콜 차원만
> 검증했고 실 auth-web/Supabase 연동은 여전히 미배포·CTO 승인 대기.

이 문서는 AIR-0225B(service_role 유출 사고)와 AIR-0226(Hermes 보안 설계)의 연장선이다. 핵심
교훈 재확인: **AIR Worker가 운영자 소유의 렌더링 PC에서 돈다는 사실이 "신뢰해도 된다"는
뜻이 아니다.** 물리적으로 원격지에 있고, 도난/재판매/침해 가능성이 있는 일반 PC이므로
AIR-0225B가 데스크톱 AIR Studio에 적용한 것과 같은 원칙("이 실행 환경은 RLS 우회 자격증명을
가질 자격이 없다")을 그대로 적용한다.

## 1. Worker 인증 — 제한된 Worker Token

AIR Worker는 **Supabase service_role, 관리자 마스터 키, 결제 API 키 중 어느 것도 갖지
않는다**(핵심 결정 #8, 금지사항 그대로). 대신 중앙 서버가 발급하는 **Worker Token**만 사용한다.

**Worker Token이 허용하는 것**:
- `worker_id` 확인(자기 자신이 누구인지 증명)
- 허용된 `job_type`만 수신(예: 이 워커가 렌더링 전용이면 `topic_*` job을 아예 못 받음 — 토큰에
  스코프를 인코딩)
- **자신에게 할당된 작업만** 조회(다른 워커의 작업 조회 불가)
- 작업 진행률/결과 전송
- heartbeat 전송
- 제한된 topic context 조회(AIR-0226 §SECURITY §2의 화이트리스트와 동일 원칙 — 카테고리
  메타/채널기억 요약/사용이력 요약만, PII·결제·추천인 데이터 제외)

**Worker Token이 절대 허용하지 않는 것**(금지사항 그대로):
- Supabase service_role
- 관리자 마스터 키
- 결제 API 키
- 다른 Worker의 작업 조회
- 다른 tenant의 데이터 조회
- 운영 DB 임의 쿼리(테이블을 직접 SELECT하는 것 자체가 불가능해야 함 — 토큰은 REST 테이블
  접근권이 아니라 **제한된 API 엔드포인트 호출권**이어야 한다, AIR-0226의 "Hermes는 제한된
  내부 API만 호출" 원칙과 동일 구조를 중앙 서버-Worker 관계에도 적용)

**토큰 형태 제안**: AIR-0225B에서 만든 데스크톱 세션 토큰(`auth-web/lib/desktopSession.ts`)과
유사한 HMAC 서명 방식을 재사용 검토 — 다만 Worker Token은 사용자 이메일이 아니라 `worker_id`
+ 허용 `job_type` 목록 + tenant_id를 payload에 인코딩하는 것으로 확장. 정확한 구현은 실 연동
단계(다음 Task)에서 결정, 이번 문서는 요구사항만 정의.

## 2. Local API — 127.0.0.1 전용

```
GET  /health
GET  /status
GET  /processes
POST /processes/render/start
POST /processes/render/stop
POST /processes/hermes/start
POST /processes/hermes/stop
GET  /jobs
GET  /logs
POST /shutdown
```

- **바인딩은 반드시 `127.0.0.1`(loopback)에만** — `0.0.0.0`이나 실제 네트워크 인터페이스
  주소로 바인딩하지 않는다. uvicorn 기동 시 `host="127.0.0.1"`을 하드코딩하고, 이걸 설정으로
  바꿀 수 있는 옵션 자체를 노출하지 않는 것을 제안(실수로 외부 공개되는 사고를 원천 차단).
- **외부 네트워크에 공개하지 않는다**(금지사항) — 방화벽 규칙에 의존하지 않고, 애초에
  바인딩 주소 자체로 강제한다(AIR-0225B의 "자격증명을 아예 안 줌으로 방어" 철학과 같은
  결의 — "설정으로 막기"보다 "물리적으로 못 하게 하기"를 우선).
- `POST /shutdown`처럼 파괴적인 엔드포인트가 있으므로, loopback 전용이라 해도 같은 PC의
  다른 프로세스가 실수로/악의적으로 호출할 가능성은 남는다 — 로컬 전용 토큰(예: 기동 시
  랜덤 생성해 로컬 파일에만 저장하는 shared secret)을 헤더로 요구하는 것을 다음 단계에서
  검토(이번 스켈레톤은 loopback 바인딩만으로 최소 방어선 구현, 토큰 게이트는 후속 과제로
  명시).

## 3. 중앙 서버 연동 시의 원칙 (이번 Task는 미연결, 설계만)

- AIR Worker → 중앙 서버 호출은 전부 HTTPS + Worker Token.
- 중앙 서버 → AIR Worker로의 직접 호출은 없음(AIR Worker가 폴링하는 pull 모델 — Stage 1에서
  확인한 기존 `remote_drive_worker.py`의 폴링 패턴을 그대로 계승, push 모델(죽은 코드였던
  `/remote/render`)은 재사용하지 않음).
- `topics_queue` 승격은 중앙 서버(관리자 승인 경유)만 수행 — AIR Worker(Hermes Worker
  Process 포함)는 이 테이블에 쓸 권한이 원천적으로 없다(금지사항 "topics_queue 자동 승격
  금지"를 Worker Token 스코프 자체로 강제).

## 4. 실 Worker Token 커밋 금지 (금지사항)

이번 스켈레톤 구현(§12)은 실제 Worker Token을 생성/저장/커밋하지 않는다 — 로컬 모의 토큰
(`"poc-worker-token-not-real"` 같은 명백히 가짜인 플레이스홀더)만 사용하고, 이마저도 코드에
하드코딩하지 않고 로컬 설정 파일(`.gitignore` 대상)에서 읽도록 구조만 만든다.

## 5. 잔여 위험

1. ~~Local API의 `/shutdown`/`/processes/*/stop` 같은 제어 엔드포인트에 인증이 없는 채로
   출시되면...~~ **[AIR-0227C로 해소]** DPAPI 기반 로컬 토큰 게이트를 구현·실측 완료 -
   [LOCAL_API_SECURITY.md](./AIR_WORKER_LOCAL_API_SECURITY.md).
2. Worker Token 탈취 시 파급 범위는 "그 워커에게 할당된 작업 조회/결과 전송/제한된 topic
   context 조회"로 국한되지만(§1), 여러 워커가 같은 토큰을 공유하는 실수를 하면 격리가
   무너진다 — 워커별 고유 토큰 발급/회전 절차는 [AUTH.md](./AIR_WORKER_AUTH.md)에서
   설계했으나(`token_id` 필드로 재발급 시 이전 토큰 폐기 가능하도록 스키마는 준비됨),
   auth-web에 실제로 배포되지 않아 운영 절차로서는 여전히 미완성.
3. **[AIR-0227C에서 새로 발견]** lease TTL보다 긴 네트워크 장애 중에는 같은 워커가 이미
   끝낸 작업을 스스로 다시 렌더링할 수 있다 - 서버 쪽 idempotency가 "완료 기록 중복"은
   막지만 "중복 렌더링 자체"는 막지 못한다. 상세와 부분 완화책은
   [LEASE_PROTOCOL.md](./AIR_WORKER_LEASE_PROTOCOL.md) §6.
4. **[AIR-0227C]** Local API에 반복 실패 요청에 대한 rate limiting이 없다 -
   [LOCAL_API_SECURITY.md](./AIR_WORKER_LOCAL_API_SECURITY.md) §5.
