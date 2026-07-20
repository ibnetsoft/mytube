# ChatGPT Plus 구독 인증 뱃지 시스템 — 보안 설계 (SECURITY)

- 상태: **설계안 / CTO 승인 대기**
- 관련 문서: [SPEC](./CHATGPT_PLUS_VERIFICATION_SPEC.md), [QA](./CHATGPT_PLUS_VERIFICATION_QA.md)

---

## 1. BLOCKER: 데스크톱 앱은 "신뢰할 수 없는 실행 환경"이다

이번 조사에서 나온 가장 중요한 발견이며, 이 문서 전체와 SPEC 문서의 아키텍처 결정에 직접
영향을 준다.

### 1.1 사실관계

- `.github/workflows/windows-release.yml` 107~117행과 `tools/build_windows.ps1` 179~214행은
  빌드 시 `SUPABASE_SERVICE_ROLE_KEY`를 **패키징되는 Windows 데스크톱 앱의 `.env` 파일에 그대로
  기록**한다. 워크플로 자체 주석에 "다른 Supabase 연동 기능(추천인 커미션, 토큰 잔액, 프로젝트 동기화)이
  아직 서버 프록시로 이전되지 않아 어쩔 수 없이 감수하는 위험"이라고 명시되어 있다.
- 즉 **모든 최종 사용자의 PC에 RLS를 완전히 우회하는 `service_role` 키가 배포되어 있다.**
- AIR Studio의 "FastAPI 백엔드"(`main.py`)는 클라우드에 호스팅된 서버가 아니라, **사용자 자신의
  PC에서 로컬로 실행되는 프로세스**다. 즉 이 앱 안에서 도는 "서버 사이드" 코드는 실행 환경 관점에서
  전적으로 사용자 통제 하에 있다 (디버거로 붙이기, 바이너리 패치, `.env` 파일 열람 등 모두 가능).

### 1.2 왜 문제인가

지시사항 §4는 "FastAPI 백엔드 또는 안전한 서버 작업자에서 Gemini를 호출하고, API 키와
service_role 키를 프론트엔드에 노출하지 않는다"고 요구한다. 이 요구사항 자체는 타당하지만,
**"FastAPI 백엔드"를 데스크톱 앱의 로컬 FastAPI 프로세스로 해석하면 요구사항을 지켰다고
착각하게 되는 함정**이 있다. 실제로는:

- 자동 승인 임계값(95점), 규칙 채점 로직, "APPROVED면 badge 발급" 같은 판정 코드가 로컬
  프로세스 안에 있다면, 사용자가 그 바이너리/코드를 패치해서 항상 `APPROVED`를 반환하게
  만들 수 있다.
- 데스크톱 앱이 이미 들고 있는 `service_role` 키를 그대로 쓴다면, 사용자는 앱을 거치지 않고
  **Supabase REST API에 직접 그 키로 `subscription_verifications`/`user_badges`에 자기 자신을
  `APPROVED`로 만드는 row를 직접 INSERT/UPDATE**할 수 있다. RLS는 `service_role`에 대해
  아무 의미가 없다.
- 즉 "Gemini 분석 + 규칙 기반 점수로 자동판정하고, 애매하면 관리자 검토로 보낸다"는 이번
  기능의 핵심 보안 요구사항이, 실행 위치를 잘못 선택하면 **처음부터 완전히 무력화**된다.

### 1.3 권장 결론

> **뱃지 발급 여부를 결정하는 모든 로직(파일 무결성 검증, Gemini 호출, 규칙 채점, 상태 전이,
> `user_badges` 기록)은 `auth-web`(Next.js, ibnetsoft가 호스팅하는 서버)에서만 실행한다.**
> 데스크톱 앱의 FastAPI 레이어는 얇은 프록시로만 쓴다 — 사용자의 (service_role이 아닌) 개인
> Bearer 토큰을 실어 auth-web API에 파일을 전달하고, 응답을 화면에 보여주는 역할만 한다.
> 데스크톱 앱 코드 안에는 Gemini 키도, 판정 임계값도, service_role 키를 쓰는 Supabase 쓰기
> 호출도 두지 않는다.

이는 SPEC §5의 API 배치(§5.1/§5.3을 auth-web에, §5.2는 단순 프록시로) 로 이미 반영해 두었다.
**CTO 결정이 필요한 지점은, 이 결론에 동의하는지, 아니면 다른 완화책(예: 데스크톱 앱은 아예
service_role 키를 이 기능에서는 쓰지 않도록 별도의 제한된 anon 키/사용자 토큰만 쓰게 하고
그 상태로 로컬에서 판정까지 하는 절충안)을 원하는지다.** 후자를 택하더라도 최소한
"자동 승인" 판정과 `user_badges` 기록만큼은 반드시 서버(auth-web)에서 최종 확정해야 하며,
로컬에서 계산한 점수는 참고용으로만 취급하고 신뢰하지 않아야 한다.

---

## 2. 사용자 접근 통제

- `subscription_verifications`, `user_badges` 모두 RLS 활성화 + `auth.uid() = user_id` 조건의
  SELECT 정책만 부여. INSERT는 신규 제출 시에만, 반드시 `WITH CHECK (auth.uid() = user_id AND status = 'UPLOADED')`
  로 제한해 사용자가 임의 상태값으로 row를 만들 수 없게 한다.
- UPDATE/DELETE 정책은 사용자에게 **전혀 부여하지 않는다.** 상태 전이(승인/반려/재분석/만료/취소)는
  전부 auth-web의 service_role 백엔드 코드로만 수행 — RLS를 신뢰 경계로 삼지 않고, "일반 사용자
  role로는 애초에 UPDATE 권한이 없다"를 DB 레벨에서 강제한다.
- Storage(`subscription-verifications` 버킷)도 동일 원칙: `storage.objects`에 대해 `anon`/`authenticated`
  정책을 아예 만들지 않는다. 업로드/다운로드 모두 서버가 대행하므로 클라이언트 직접 접근 경로가 없다.
- "승인 후 원본 교체 금지"는 애플리케이션 레벨에서 강제한다: `status IN ('APPROVED','EXPIRED','REVOKED')`
  인 verification은 재업로드 API가 새 row 생성만 허용하고 기존 row의 `storage_path`/`file_sha256`
  갱신을 절대 하지 않는다 (§SPEC 2 상태머신 참고).

## 3. 관리자 접근 통제

- 기존 컨벤션 그대로 `auth-web/app/api/admin/_auth.ts`의 `requireAdmin`/`requireSuperAdmin`을
  모든 신규 `/api/admin/subscription-verifications/*` 라우트에 반드시 통과시킨다.
- **반려/재분석/목록조회**는 `requireAdmin`(서브어드민 포함), **인증 취소(REVOKE)/만료일 수동 수정**은
  `requireSuperAdmin`으로 더 엄격하게 제한한다 (뱃지를 박탈하거나 유효기간을 임의로 늘리는 조작은
  파급력이 크므로).
- 조사 결과 `users/ban`, `users/[id]/settings`, `users/[id]/logs` 라우트가 인증 체크 없이
  service_role 키로 직접 동작하는 기존 결함을 발견했다 (§SPEC 1.2). **이번 신규 라우트들은
  이 패턴을 절대 참고하지 않는다** — 매 핸들러 최상단에 `requireAdmin`/`requireSuperAdmin` 호출을
  코드리뷰 체크리스트 항목으로 강제한다.

## 4. 개인정보 최소화

- **이메일**: Gemini가 증빙에서 읽은 계정 이메일은 마스킹된 형태(`ab***@gmail.com`)로만
  `masked_account_email`에 저장한다. 원문 이메일은 DB에 저장하지 않고, 본인 확인용으로는
  `account_email_hash = sha256(lower(trim(추출된_이메일)))`만 저장해 `profiles.email`의 동일 해시와
  비교하는 용도로만 쓴다 (완전 일치 여부만 필요, 원문 비교 불필요).
- **이미지 원본**: DB에 base64로 저장하지 않는다(지시사항 금지 사항). Private Storage 버킷에만
  저장하고 DB에는 경로 문자열만 둔다.
- **Gemini 원본 응답**: `ai_raw_response`(JSONB)에 저장하되, 프롬프트에서 Gemini에게 "이미지에서
  발견한 부가 개인정보(주소, 카드번호 뒷자리 등)를 추출 목록에 없는 필드로는 응답하지 말 것"을
  명시적으로 지시해 애초에 불필요한 PII가 응답에 섞이지 않도록 한다.
- **Signed URL**: 관리자 조회용으로만, 5분 내외의 짧은 만료로 요청 시점에 매번 새로 발급한다.
  발급 자체도 `requireAdmin` 뒤에서만 가능하며, 발급 이벤트를 감사 로그에 남길지는 QA 단계에서
  결정한다(과도한 로그 양산 우려와 트레이드오프, CTO 결정 항목 아님 — 구현 세부사항).

## 5. 파일 업로드 보안

- **허용 포맷**: JPG/PNG/WEBP/PDF, 최대 10MB (지시사항 그대로).
- **실제 MIME 검사**: 조사 결과 이 저장소의 기존 업로드 엔드포인트들은 전부 확장자만 보고 있고
  (`app/utils.py`의 `validate_upload()` 포함) 매직바이트 검사가 어디에도 없다. 이번 기능은 최초로
  진짜 콘텐츠 검사를 추가해야 한다:
  - 이미지: 파일 헤더 매직바이트로 JPEG(`FFD8FF`)/PNG(`89504E47`)/WEBP(`RIFF....WEBP`) 판별.
  - PDF: `%PDF-` 헤더 확인 + (가능하면) 페이지 렌더링 가능 여부까지 검증해 "확장자만 .pdf인 실행파일"을
    걸러낸다.
  - Python 표준 라이브러리만으로 부족하면 `python-magic` 또는 Pillow의 `Image.open().verify()`
    도입을 검토 (신규 의존성 추가이므로 CTO/팀 확인 필요 — BLOCKER 목록 참고).
- **SVG/실행 가능 포맷 명시적 차단**: 확장자 화이트리스트에 SVG를 포함하지 않는 것만으로는 부족하다
  (확장자를 속여 `.jpg`로 이름 붙인 SVG/스크립트가 매직바이트 검사를 통과 못 하게 해야 진짜 차단이다).
  이번 기능의 매직바이트 검사가 이 요구사항의 실질적 구현 지점이다.
- **경로 주입 방지**: `storage_path`는 서버가 `verification_id`(서버 생성 UUID)로 조립하며, 클라이언트가
  보낸 파일명을 경로에 그대로 쓰지 않는다 (기존 `thumbnail-style-presets/custom` 엔드포인트처럼
  타임스탬프/UUID로 새로 만든 파일명만 사용).

## 6. 사기(fraud) 탐지

- **동일 SHA-256 이미지 재사용**: 신규 제출마다 `file_sha256`으로 다른 `user_id`의 기존 row와
  대조. 매치되면 `duplicate_image_flag=true`로 저장하고 규칙 엔진이 **무조건** `NEEDS_REVIEW`로
  보낸다(95점 이상이어도 자동승인 금지 — 지시사항 §5 그대로).
- **위조 위험**: Gemini의 `visual_tampering_risk`가 `medium`/`high`이면 자동승인 배제.
- **필수 날짜 미확인**: `payment_date`/`next_renewal_date`/`billing_period_end` 중 유효기간
  계산에 필요한 필드가 전부 비어 있으면 자동승인하지 않고 관리자 검토로 보낸다 (지시사항 §5,
  §6 "둘 다 없으면 관리자 검토"와 일치).
- **AI 단독 확정 금지 문구**: 사용자/관리자에게 노출되는 모든 문구에서 "Gemini가 위조 여부를
  최종 판정했다"는 뉘앙스를 쓰지 않는다. 예: "AI 분석 결과 + 검증 규칙을 참고용으로 제공하며, 최종
  승인은 규칙 기준 점수와 관리자 검토를 거칩니다." (지시사항 금지 문구 항목과 직결)

## 7. 감사 로그

- `subscription_verification_audit_logs`(SPEC §3.3)에 상태 전이 이벤트 전부 기록:
  업로드, 분석 시작, 자동승인, 검토전환, 승인, 반려, 취소, 재분석, 만료, 만료일 수정.
- `actor_id`가 NULL이면 시스템/배치 작업(예: 일일 만료 스윕)임을 의미하도록 컨벤션 고정.
- 감사 로그 테이블 자체는 RLS 활성화 + 정책 없음(service_role 전용) — `referral_audit_logs`와
  동일 컨벤션, 사용자 본인도 직접 조회 불가(필요하면 verification 상세 조회 API 응답에
  일부 요약만 포함).

## 8. Service Role 키 노출 점검 결과

- auth-web 쪽은 점검 결과 클라이언트 컴포넌트(`"use client"` 파일)나 `static/js/**`,
  `templates/**` 어디에도 `SUPABASE_SERVICE_ROLE_KEY` 문자열이 없음 — 웹 프론트엔드 노출은
  없다고 확인.
- **유일한 실제 노출 경로는 §1에서 다룬 데스크톱 앱 `.env` 번들**이며, 이는 이번 기능이 만든
  문제가 아니라 기존에 존재하던, 문서화된 "감수 중인 위험"이다. 다만 이번처럼 "뱃지를 자동으로
  발급하는" 민감한 기능을 설계할 때는 그 기존 위험이 직접적인 공격 표면이 되므로 반드시 §1의
  아키텍처 결론을 따라야 한다.
- 부가 발견: `auth-web/lib/supabaseAdmin.ts`가 `SUPABASE_SERVICE_ROLE_KEY`가 비어있으면
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`로 조용히 폴백하는 코드가 있음. 이 폴백 상태에서는 오히려
  서버 라우트가 RLS를 우회하지 못해 이번 기능의 승인/취소 API가 조용히 실패(혹은 권한 부족 에러)할
  수 있다 — 신규 기능 배포 전 auth-web 배포 환경에 `SUPABASE_SERVICE_ROLE_KEY`가 실제로 설정돼
  있는지 확인 필요 (구현 단계 체크리스트 항목, BLOCKER는 아님).

## 9. 이번 기능이 손대지 않는 것 (명시적 범위 제한)

지시사항의 "임의 변경 금지" 항목을 설계 수준에서 다음과 같이 보장한다:

- 기존 인증(로그인/세션) 로직 — 무변경. `_auth.ts`의 기존 `requireAdmin`/`requireSuperAdmin`을
  "호출"만 하고 그 구현은 건드리지 않는다.
- 추천인(referral) 스키마/로직 — 무변경. `referral_audit_logs`를 재사용하지 않고 별도 테이블을
  둔 이유가 바로 이 격리다.
- 결제/토큰(`token_transactions`, `profiles.token_balance` 등) — 무변경. 이번 기능은 토큰을
  소모하거나 지급하지 않는다(단, Gemini Vision 호출 자체의 비용/크레딧 처리 방식은 §QA에서
  기존 `auth_service.check_credits()` 패턴 재사용 여부를 CTO 결정 항목으로 남긴다).
- 사용자 권한 체계(`membership_tier`, `is_superadmin` 등) — 무변경. `CHATGPT_PLUS_VERIFIED`
  뱃지는 `membership_tier`와 별개 축이며, 뱃지 보유가 등급을 자동으로 바꾸지 않는다(적어도
  1차 구현 범위에서는 — 뱃지 보유자에게 별도 혜택을 줄지는 이번 설계 범위 밖의 상품 정책 결정).
