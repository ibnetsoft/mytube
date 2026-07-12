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

## 6. AIR-0227D-VALIDATION에서 발견·수정한 보안 사고 (별도 긴급 커밋)

AIR-0227D 작업 중(신규 Worker API를 auth-web에 붙이는 과정에서 기존 auth-web 코드를
훑어보다가) 발견한, **이 Task의 신규 코드와 무관한 기존 auth-web의 실제 프로덕션
취약점 2건**. 전부 즉시 수정 완료, 별도 긴급 커밋으로 분리.

### 6.1 관리자 API 무인증 (심각)

- **`/api/admin/render-queue`**(GET/DELETE): `requireAdmin`/`requireSuperAdmin` 호출이
  전혀 없이 service_role 클라이언트로 직행 - 로그인 없이 누구나 렌더 큐 전체를 조회하고
  임의 행을 삭제할 수 있었다. 프론트(`DashboardContent.tsx`의 `adminFetch`)는 이미
  `Authorization: Bearer <세션토큰>`을 보내고 있었으므로, 서버가 그걸 검증만 안 하고
  있던 상태 - 수정은 프론트 변경 없이 서버에 `requireSuperAdmin` 게이트만 추가.
- **`/api/admin/users/ban`**(POST): 같은 패턴 - 로그인 없이 임의 `userId`를 밴/언밴 가능.
  전체 저장소를 grep해도 이 라우트를 호출하는 현재 코드가 없어(죽은 로컬 patch 파일에만
  참조가 남아있음) 호환성 리스크 없이 즉시 게이트 추가.
- 두 라우트 모두: `requireSuperAdmin` 게이트, 실패 시 401/403(기존 `_auth.ts` 응답 형식과
  동일), destructive action(DELETE/ban)은 요청자 이메일 + 대상 id를 서버 로그에 기록
  (`[admin-audit] action=... requester=... detail=...` 형식 - 전용 감사 테이블은 아직
  없음, 긴급 수정 범위 밖으로 명시).
- QA: 로컬 dev 서버로 무인증 GET/DELETE/POST가 401/403으로 막히는 것을 실측 확인(Supabase
  자격증명이 이 환경에 없어 "정상 관리자 토큰으로 성공" 경로는 staging에서 재확인 필요).

### 6.2 `service_role` 미설정 시 anon key로 조용한 폴백 (심각)

`lib/supabaseAdmin.ts` + 7개 라우트 파일이 전부 `process.env.SUPABASE_SERVICE_ROLE_KEY ||
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!` 패턴을 썼다 - `SUPABASE_SERVICE_ROLE_KEY`가
배포 환경에 누락되면(설정 실수, 환경 분리 실수 등) 관리자/내부 전용 기능이 **에러 없이
익명 권한으로 조용히 계속 동작**했을 것 - RLS가 있는 테이블은 대부분 막히겠지만 RLS가
없거나 허술한 테이블/함수가 있다면 그대로 뚫린다. 8개 파일 전부
`process.env[name] || 실패` 대신 **즉시 throw**하는 `requireEnv()`로 교체, 나머지 7개
라우트는 중복 클라이언트 생성 대신 이 공유 `supabaseAdmin`을 import하도록 통합(관리자
client와 일반 client의 경계가 이제 코드 구조로도 명확 - 서비스 전용 client는 이 파일
하나뿐).

QA: dev 서버에 Supabase 환경변수가 아예 없는 상태(이 환경의 실제 상태)로 8개 라우트 중
2개를 직접 호출 - 전부 "anon key로 계속 진행" 대신 `NEXT_PUBLIC_SUPABASE_URL is not
configured - refusing to start a privileged Supabase client (no anon-key fallback)`로
즉시 명시 실패(500)함을 실측 확인. "service_role 정상 설정" 성공 경로는 이 환경에 실
자격증명이 없어 검증 못함 - staging에서 재확인 필요.

### 6.2-A AIR-0227D-VALIDATION 계속: 추가 정적 확인 3 — `/api/admin/**` 전수조사

§6.1이 발견한 2건 외에 동일 취약점이 더 있는지 39개 admin 라우트 파일 전부를 조사했다 -
**6개 파일, 9개 엔드포인트에서 추가로 발견**, 전부 즉시 수정. 이 중 2개(`admin/settings`,
`admin/users/[id]/settings`)는 **다른 사용자의 실제 API 키 원문 + PIN코드(실제 로그인
비밀번호)를 무인증으로 조회·변조 가능**했던 가장 심각한 등급.

| 경로 | Method | 읽기/파괴적 | 적용 인증 | 요구 역할 | 감사 로그 |
|---|---|---|---|---|---|
| `admin/categories` | GET,POST,DELETE,PUT | 혼합 | requireAdmin/requireSuperAdmin | 혼합 | ✗ |
| `admin/learning` | GET | 읽기 | requireAdmin | admin | ✗ |
| `admin/logs` | GET | 읽기 | requireAdmin | admin | ✗ |
| `admin/logs` **[이번 라운드 수정]** | GET | 읽기 | requireAdmin | admin | ✗ |
| `admin/music-plan-templates` **[이번 라운드 수정]** | GET,POST,DELETE | 혼합(POST/DELETE 파괴적) | requireSuperAdmin | super admin | ✗ |
| `admin/publishing` | GET,POST,PATCH | 혼합 | requireAdmin/requireSuperAdmin | 혼합 | ✗ |
| `admin/referrals/*` (7개 파일) | GET/PATCH | 대부분 읽기 | requireAdmin(대부분)/requireSuperAdmin(withdrawals/[id], 최상위 PATCH) | 혼합 | ✗ |
| `admin/render-queue` **[직전 라운드 수정]** | GET,DELETE | 혼합(DELETE 파괴적) | requireSuperAdmin | super admin | ✅(DELETE) |
| `admin/settings` **[이번 라운드 수정, 심각]** | GET,POST | 혼합(GET이 API키 원문 반환, POST 변조) | requireSuperAdmin | super admin | ✗ |
| `admin/settings/global` | GET,POST | 혼합 | requireSuperAdmin | super admin | ✗ |
| `admin/settings/referral` | GET,POST | 혼합 | requireAdmin | admin | ✗ |
| `admin/settlements` | GET | 읽기 | requireSuperAdmin | super admin | ✗ |
| `admin/settlements/payout` | POST | 파괴적(잔액 지급) | requireSuperAdmin | super admin | ✗ |
| `admin/style-presets` | GET,POST,DELETE | 혼합 | requireSuperAdmin | super admin | ✗ |
| `admin/tenants`, `admin/tenants/[key]` | GET,POST,PATCH,DELETE | 혼합 | requireSuperAdmin | super admin | ✗ |
| `admin/topics-queue` | GET,POST,PUT,DELETE,PATCH | 혼합 | requireAdmin/requireSuperAdmin | 혼합 | ✗ |
| `admin/users` | GET | 읽기 | requireAdmin | admin | ✗ |
| `admin/users/admin-role` | POST | 파괴적(권한 변경) | requireSuperAdmin | super admin | ✗ |
| `admin/users/api-keys` | POST | 파괴적(API키 변조) | requireSuperAdmin | super admin | ✗ |
| `admin/users/approval` | POST | 파괴적(가입승인) | requireAdmin | admin | ✗ |
| `admin/users/ban` **[직전 라운드 수정]** | POST | 파괴적(계정 정지) | requireSuperAdmin | super admin | ✅ |
| `admin/users/recharge` | POST | 파괴적(토큰 충전) | requireSuperAdmin | super admin | ✗ |
| `admin/users/role` | POST | 파괴적 | requireSuperAdmin | super admin | ✗ |
| `admin/users/superadmin` | PATCH | 파괴적 | requireSuperAdmin | super admin | ✗ |
| `admin/users/update-metadata` | POST | 파괴적 | requireAdmin | admin | ✗ |
| `admin/users/[id]/logs` **[이번 라운드 수정]** | GET | 읽기 | requireAdmin | admin | ✗ |
| `admin/users/[id]/settings` **[이번 라운드 수정, 심각]** | GET,POST | 혼합(GET이 API키+PIN 원문 반환, POST 변조) | requireSuperAdmin | super admin | ✗ |
| `admin/users/[id]/transactions` **[이번 라운드 수정]** | GET | 읽기 | requireAdmin | admin | ✗ |
| `admin/voices` | GET,POST,DELETE | 혼합 | requireSuperAdmin | super admin | ✗ |
| `admin/withdrawals` | GET,PATCH | 혼합 | requireAdmin | admin | ✗ |
| `admin/worker-tokens`, `admin/worker-tokens/[tokenId]` (AIR-0227D 신규) | GET,POST,DELETE | 혼합 | requireSuperAdmin | super admin | ✗(토큰 발급/폐기는 원문 토큰 미로깅이 곧 최소한의 안전장치) |
| `admin/workers` (AIR-0227D 신규) | GET | 읽기 | requireAdmin | admin | ✗ |

**결과: POST/PATCH/PUT/DELETE 무인증 라우트 0건, 민감한 GET 무인증 라우트 0건** (39개 파일
전수, `grep`으로 `requireAdmin`/`requireSuperAdmin` 부재 재확인 - 전부 존재).

**감사 로그는 render-queue DELETE와 users/ban POST 2곳뿐** - 나머지는 admin 인증 게이트는
있지만 "누가 언제 무엇을 바꿨는지"의 별도 기록은 없다(Supabase 자체 로그에 요청이 남을
수는 있으나 이 앱 레벨에서 구조화된 감사 로그는 아님). 특히 `admin/users/admin-role`,
`admin/users/role`, `admin/users/superadmin`(권한 상승/강등), `admin/settlements/payout`,
`admin/users/recharge`(금전적 영향)는 감사 로그가 없는 파괴적 라우트로 남아있다 - 이번
라운드 범위(무인증 게이트 폐쇄)를 넘어서는 별도 개선 과제로 플래그만 해둔다.

### 6.3 QA에서 확인하지 못한 항목 (정직하게 명시)

- 만료된 관리자 세션, 변조된 JWT에 대한 거동 - `requireAdmin`이 내부적으로
  `supabase.auth.getUser(token)`을 호출하므로 이미 Supabase Auth가 처리하는 부분이라
  별도 코드 경로는 없지만, 실제 만료 토큰으로 재현 테스트는 안 함(실 Supabase 프로젝트
  필요).
- "일반 사용자(비관리자) 토큰으로 시도" - 실 사용자 계정이 있는 staging에서만 재현 가능.
- 기존 관리자 UI 회귀 - 코드 리뷰로 `adminFetch`가 이미 Bearer 헤더를 보내고 있음을
  확인했을 뿐, 실제 브라우저로 렌더 큐 탭을 열어보지는 못함(dev 서버에 실 Supabase 연결
  없음).
