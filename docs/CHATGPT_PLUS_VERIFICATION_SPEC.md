# ChatGPT Plus 구독 인증 뱃지 시스템 — 기능 명세 (SPEC)

- 상태: **Stage 1~4 구현 완료.** Stage 1(2026-07-15): `migrations/air_0228_chatgpt_plus_verification_stage1*.sql` 프로덕션 반영 확인됨(테이블 3개 생성+빈 상태 확인, Private Storage 버킷 확인). Stage 2~4(커밋 `b32cad77`): auth-web 사용자 API(`lib/subscriptionVerification.ts` Gemini Vision 분석/규칙 점수, `lib/uploadValidation.ts` 매직바이트 MIME 검사) + 데스크톱 앱 업로드 UI(`settings.html`/`settings_page.js`/`app/routers/settings.py` 프록시) + 웹어드민 승인/반려 화면(`app/admin/subscription-verifications`) 코드 구현 완료. 단, 검증은 `npx tsc --noEmit`/Python ast/Jinja2 파싱 등 **정적 검증까지만** — Gemini Vision 실호출, 실제 파일 업로드/Storage 라운드트립, 관리자 승인/반려 클릭까지 가는 라이브 테스트는 아직 없음. Stage 5(만료 배치)·Stage 6(QA 전체 시나리오+기능 플래그 해제)는 미착수.
- 관련 문서: [SECURITY](./CHATGPT_PLUS_VERIFICATION_SECURITY.md), [QA](./CHATGPT_PLUS_VERIFICATION_QA.md)
- 작성 근거: 저장소 조사 결과 (아래 각 절에 실제 파일 경로 인용)

> **먼저 읽을 것**: 이 기능의 승인/자동판정 로직을 "어디서" 실행할지에 대해
> [SECURITY.md §1 (아키텍처 BLOCKER)](./CHATGPT_PLUS_VERIFICATION_SECURITY.md#1-blocker-데스크톱-앱은-신뢰할-수-없는-실행-환경이다)
> 에서 근본적인 문제를 제기합니다. 이 SPEC은 그 블로커의 권장 해법(승인 로직은
> `auth-web`에서 실행)을 전제로 작성되었습니다. CTO가 다른 방향을 택하면 API 위치가
> 바뀔 뿐 DB 스키마/상태 머신은 동일하게 재사용 가능합니다.

---

## 0. 용어

| 용어 | 의미 |
|---|---|
| Desktop App | `main.py` 기반 FastAPI + Jinja2, 사용자 PC에 설치되어 로컬로 구동되는 "AIR Studio" |
| auth-web | `auth-web/` Next.js 앱. 로그인/과금/추천인/관리자 패널을 담당하는 **호스팅된** 서버 |
| Supabase | 공용 Postgres + Storage + Auth 백엔드 |
| provider | 인증 대상 구독 서비스 (`chatgpt_plus`, 확장 시 `chatgpt_pro`/`gemini_advanced`/`claude_pro`) |

---

## 1. 현재 저장소 조사 결과 요약

### 1.1 세팅 > 일반 설정 화면
- 실제 파일: [`templates/pages/settings.html`](../templates/pages/settings.html) (단일 페이지, 클라이언트 탭 전환 방식).
  탭 버튼은 27~63행, "일반 설정"에 해당하는 것은 `api` 탭(라벨 `label_tab_basic_settings`, "🎫 기본 설정").
- 사용자 정보 카드가 이미 이 탭 안 185~274행에 있음 (`userName`/`userNationality`/`userPhone`/`userEmail`,
  `stSaveUserProfile()` → `POST /api/auth/profile`). **새 "외부 서비스 인증" 카드는 이 섹션 바로 뒤에
  추가하는 것이 기존 UI 관례와 가장 자연스럽게 맞는다.**
- 파일 업로드 UI 관례: `customStyleImageStyle`/`customStyleImageChar` (590~612행) — 숨김
  `<input type=file>` + 클릭 가능한 미리보기 div, `static/js/settings_page.js`의
  `handleStyleImageSelect()`(655~671행)가 `FileReader.readAsDataURL`로 즉시 미리보기.
- 백엔드: [`app/routers/settings.py`](../app/routers/settings.py) (`prefix=/api/settings`).
  기존 업로드 엔드포인트(`/style-presets/custom`, `/thumbnail-style-presets/custom`, `/crop-grid`)는
  **실제 MIME 검사 없이 확장자/파일명만 다룬다** — 재사용 금지 대상.
  진짜 확장자 화이트리스트 + 용량 제한 헬퍼는 [`app/utils.py`](../app/utils.py) 26~43행의
  `validate_upload()` / `ALLOWED_IMAGE_EXT` / `MAX_IMAGE_SIZE` 이지만 이것도 **매직바이트 검사는 안 함** →
  이번 기능에서 실제 MIME 스니핑을 새로 추가해야 한다 (§4.4).
- Gemini Vision 호출 관례: [`services/gemini_service.py`](../services/gemini_service.py)
  `generate_text_from_image()` (225~278행, 단일 이미지, 동작 확인됨) +
  `analyze_webtoon_panel()` (280~420행)의 "프롬프트 끝에 JSON 스키마 명시 → 정규식으로
  `\{.*\}` 추출 → `json.loads()`" 패턴이 이 저장소 전체의 표준 방식이다. **Gemini 네이티브
  `response_schema`/구조화 출력 기능은 이 저장소 어디에도 쓰인 적이 없음** — 이번 기능은
  요구사항(JSON Schema 기반 응답 강제)상 네이티브 구조화 출력으로 업그레이드할 좋은 기회이며,
  실패 시 기존 정규식 추출 방식으로 폴백하는 이중 방어가 안전하다.
- 사용자 식별: [`services/auth_service.py`](../services/auth_service.py)는 **이메일 문자열만
  캐시**하고 Supabase UUID는 들고 있지 않음. UUID가 필요하면
  [`services/web_admin_client.py`](../services/web_admin_client.py)의
  `resolve_user_id(email=...)` (458~465행) 또는 `fetch_profile_by_email()` (423~433행)으로
  온디맨드 조회해야 한다.
- i18n: [`services/i18n.py`](../services/i18n.py)의 `PLATFORM_TRANSLATIONS` 딕셔너리
  (ko/en/vi/th 4블록)에 새 키를 추가하고 템플릿에서 `{{ t('key') }}`로 사용. 이 파일 안에
  `window_lang == 'vi'` 식의 인라인 삼항 분기 안티패턴이 섞여 있는데 **새 기능은 따라하지 말 것**.

### 1.2 웹어드민 사용자 관리
- `app/admin/users/` 같은 전용 페이지는 **없다**. 사용자 관리 UI는
  [`auth-web/components/DashboardContent.tsx`](../auth-web/components/DashboardContent.tsx)
  라는 4,759줄짜리 단일 컴포넌트(회원 관리 리스트: 3202~3360행) 안에 들어있다.
- 반면 최근에 만들어진 [`auth-web/app/admin/referrals/`](../auth-web/app/admin/referrals/)는
  `layout.tsx`(탭 네비게이션) + `page.tsx`/`organization/`/`commissions/`/`withdrawals/`/`audit/`/`settings/`
  + 공용 `_components.tsx`(`Card`/`StatusBadge`/`Pagination` 등) + `_hooks.ts`(`useAuthToken`,
  `authedFetch`) 로 구성된 **모듈형 패턴**이다.
  → **이번 기능은 `DashboardContent.tsx`에 얹지 말고 `app/admin/subscription-verifications/` 같은
  독립 라우트로, `referrals`와 같은 구조로 만든다.**
- 관리자 인증: [`auth-web/app/api/admin/_auth.ts`](../auth-web/app/api/admin/_auth.ts) —
  `Authorization: Bearer <token>` → `supabase.auth.getUser(token)` →
  `isSuperAdmin = email === SUPER_ADMIN_EMAIL`(하드코딩된 `'ejsh0519@naver.com'`) 또는
  `isSubAdmin = app_metadata.role === 'sub_admin'`. `requireAdmin()`/`requireSuperAdmin()`을
  그대로 재사용한다. (일부 기존 라우트 `users/ban`, `users/[id]/settings`,
  `users/[id]/logs`는 이 체크를 누락하고 있음 — **새 기능에서 절대 이 라우트들을 템플릿으로
  베끼지 말 것**.)
- 뱃지/entitlement 관련 기존 개념은 **전혀 없음** (grep 결과 0건, `StatusBadge`는 UI 컴포넌트명일 뿐).
  즉 이번 기능은 신규이며 기존 구조와 충돌하지 않는다.

### 1.3 Supabase Storage 현황
- 저장소 전체에서 실사용 버킷은 **`videos` 1개뿐**(공개 버킷으로 설계됨),
  [`auth-web/app/api/publishing/presigned-url/route.ts`](../auth-web/app/api/publishing/presigned-url/route.ts)
  에서 `supabaseAdmin.storage.from('videos').createSignedUploadUrl(...)`로 클라이언트에 업로드
  URL을 내려준다. **이 라우트는 관리자 인증 체크가 없고 MIME/용량 검증도 없음** — 참고용일 뿐 그대로
  복제하면 안 된다.
- Python(desktop) 쪽은 Supabase Storage를 전혀 쓰지 않는다 (`.storage.from_` 사용 0건) — 지금까지
  이미지/영상/음성은 전부 로컬 파일로만 관리되어 왔다.

### 1.4 badge/entitlement 구조
- 없음 (위 1.2 참고). `profiles.membership_tier`(`standard`/`pro`/`admin`)가 유일하게 존재하는
  "등급" 성격의 컬럼이며, 이번 뱃지와는 별개 축(구독 인증 ≠ 결제 등급)으로 설계해야 한다.
- `profiles.is_superadmin`은 코드에서 참조되지만
  [`migrations/air_0221_referral_stage1_foundation.sql`](../migrations/air_0221_referral_stage1_foundation.sql)
  133~144행 주석에 **"프로덕션에 실존하지 않음이 확인됨"** 이라고 명시되어 있다 — 스키마
  드리프트가 실제로 존재하므로, 이번 설계에서 어떤 기존 컬럼도 "존재를 가정"하지 않고 구현 시점에
  라이브 스키마를 다시 확인해야 한다.

### 1.5 기존 scheduler/cron 구조
- Supabase `pg_cron`/Edge Function: **없음**. 오히려
  [`project_handoff/AIR-0205/DUMP.md`](../project_handoff/AIR-0205/DUMP.md) 13행에
  "pg_cron 대신 FastAPI 백그라운드 태스크를 쓰기로 결정했다"는 기록이 있음.
- 실제 반복 작업 패턴은 **프로세스 내 asyncio 루프**:
  [`app/services/referral_engagement_service.py`](../app/services/referral_engagement_service.py)
  가 `interval_seconds = 3600*24` 로 `while True: ... await asyncio.sleep(24h)` 형태로
  앱 기동시 시작된다.
- `.github/workflows/`에는 스케줄 트리거(`on: schedule`)가 하나도 없다 — 전부 push/workflow_dispatch.
- **문제**: 이 asyncio 루프 패턴은 "desktop app 프로세스가 켜져 있어야 도는" 방식인데, 사용자가
  앱을 며칠씩 안 켤 수 있는 구조상 **일일 만료 처리에는 부적합**하다 (§10, SECURITY §1과 연결되는
  동일한 아키텍처 문제). auth-web 쪽에는 cron 유사 인프라가 전혀 없어 별도 확인이 필요하다
  (BLOCKER 목록 참고).

---

## 2. 상태 머신

```
UPLOADED --(Gemini 분석 시작)--> ANALYZING
ANALYZING --(점수 >= 95 & 필수조건 충족)--> APPROVED
ANALYZING --(애매/불충분)--> NEEDS_REVIEW
ANALYZING --(명백한 위조/불일치)--> REJECTED
NEEDS_REVIEW --(관리자 승인)--> APPROVED
NEEDS_REVIEW --(관리자 반려)--> REJECTED
APPROVED --(expires_at 경과, 일일 배치)--> EXPIRED
APPROVED --(관리자 강제 취소)--> REVOKED
REJECTED --(사용자 갱신 제출)--> UPLOADED (새 row 생성, 이전 row는 REJECTED로 보존)
EXPIRED --(사용자 갱신 제출)--> UPLOADED (새 row 생성)
```

- 한 유저가 같은 provider에 대해 여러 번 제출할 수 있으므로 **row는 매 제출마다 새로 생성**하고
  이력을 보존한다 (감사/사기탐지 목적상 덮어쓰기 금지). "현재 유효한 인증"은
  `user_badges` 테이블의 `ACTIVE` row 1개로 대표한다 (§3.2).
- `EXPIRING`(만료 임박)은 **DB 상태로 만들지 않는다** — `status='APPROVED' AND expires_at <= now()+7d`
  파생 조건으로 UI/알림에서만 계산한다 (지시사항 §6 요청대로).

---

## 3. 제안 DB 스키마 (Supabase Postgres)

> 명명/스타일은 `migrations/air_0221_referral_stage1_foundation.sql`,
> `auth-web/supabase_schema.sql`의 하우스 스타일을 그대로 따름: UUID PK,
> `profiles(id)` FK, `TEXT ... CHECK (... IN (...))` 상태, `metadata JSONB`,
> `created_at`/`updated_at` + 트리거, RLS는 "본인 SELECT만 정책, 나머지는 service_role only(정책 없음)".

### 3.1 `subscription_verifications` (범용, provider로 확장)

```sql
CREATE TABLE IF NOT EXISTS public.subscription_verifications (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    provider                 TEXT NOT NULL
                                 CHECK (provider IN ('chatgpt_plus','chatgpt_pro','gemini_advanced','claude_pro')),
    badge_code               TEXT NOT NULL,               -- 예: 'CHATGPT_PLUS_VERIFIED' (조회 편의용 비정규화)
    status                   TEXT NOT NULL DEFAULT 'UPLOADED'
                                 CHECK (status IN ('UPLOADED','ANALYZING','NEEDS_REVIEW',
                                                    'APPROVED','REJECTED','EXPIRED','REVOKED')),

    -- 원본 파일 (Private Storage, Public URL/base64 저장 금지)
    storage_bucket           TEXT NOT NULL DEFAULT 'subscription-verifications',
    storage_path             TEXT NOT NULL,               -- chatgpt-plus/{user_id}/{id}/original.{ext}
    file_sha256               TEXT NOT NULL,
    file_mime_type            TEXT NOT NULL,
    file_size_bytes           INT  NOT NULL,

    -- Gemini 추출 결과 (지시사항 §4 목록 그대로)
    document_type             TEXT,
    subscription_status_raw   TEXT,                       -- Gemini가 읽은 원문 상태(active/canceled 등, 참고용)
    purchase_channel          TEXT,
    masked_account_email      TEXT,                       -- 반드시 마스킹된 형태만 저장 (SECURITY §4)
    account_email_hash        TEXT,                        -- 정규화 이메일의 sha256 (동일 이메일 중복 탐지용)
    payment_date               DATE,
    billing_period_start       DATE,
    billing_period_end         DATE,
    next_renewal_date          DATE,
    currency                    TEXT,
    amount                       NUMERIC(12,2),
    required_fields_visible      BOOLEAN,

    -- AI 분석 원본 + 파생 판정
    ai_confidence                 NUMERIC(5,4),             -- 0.0 ~ 1.0
    ai_visual_tampering_risk      TEXT CHECK (ai_visual_tampering_risk IN ('low','medium','high')),
    ai_suspicious_reasons          JSONB NOT NULL DEFAULT '[]'::jsonb,
    ai_recommended_action          TEXT,
    ai_raw_response                 JSONB,                  -- Gemini 구조화 응답 원문 (감사/재현용)
    rule_score                       NUMERIC(5,2),           -- 0~100, 규칙기반 점수
    duplicate_image_flag              BOOLEAN NOT NULL DEFAULT false,  -- file_sha256이 다른 계정과 충돌

    -- 리뷰/승인
    reviewed_by                        UUID REFERENCES public.profiles(id),
    reviewed_at                         TIMESTAMPTZ,
    rejection_reason                     TEXT,

    -- 유효기간
    expires_at                            TIMESTAMPTZ,
    revoked_at                             TIMESTAMPTZ,
    revoked_reason                          TEXT,

    metadata                                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscription_verifications_user_id ON public.subscription_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_subscription_verifications_status ON public.subscription_verifications(status);
CREATE INDEX IF NOT EXISTS idx_subscription_verifications_sha256 ON public.subscription_verifications(file_sha256);
CREATE INDEX IF NOT EXISTS idx_subscription_verifications_expires_at ON public.subscription_verifications(expires_at);
```

- `duplicate_image_flag`는 신규 row 저장 시 `SELECT 1 FROM subscription_verifications WHERE file_sha256 = ? AND user_id != ?`
  으로 채움 (지시사항 §5 "동일 SHA-256 이미지 재사용 시 자동 승인 금지"). 이 플래그가 true면
  규칙 엔진이 무조건 `NEEDS_REVIEW`로 보낸다 (95점 이상이어도 자동승인 금지).
- `masked_account_email`만 저장하고 원문 이메일은 저장하지 않는다 — 대사(계정 본인 확인)는
  `account_email_hash`를 `profiles.email`의 정규화(lowercase, trim) 해시와 비교해서 수행한다
  (SECURITY §4).

### 3.2 `user_badges` (범용 뱃지 테이블 — 지시사항 §2 "재사용성 검토" 대응)

조사 결과 기존 뱃지 구조가 전혀 없으므로(§1.4), verification 전용 컬럼을 다시 얹지 않고
**독립적인 범용 뱃지 테이블**을 새로 둔다. 향후 구독 인증이 아닌 다른 뱃지(예: 이벤트 뱃지)가
생겨도 이 테이블을 그대로 재사용할 수 있다.

```sql
CREATE TABLE IF NOT EXISTS public.user_badges (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    badge_code   TEXT NOT NULL,                             -- 'CHATGPT_PLUS_VERIFIED' 등
    source_type  TEXT NOT NULL DEFAULT 'subscription_verification',
    source_id    UUID,                                       -- subscription_verifications.id (soft 참조, FK 미설정: source_type이 달라질 수 있음)
    status       TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','EXPIRED','REVOKED')),
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_badges_active_per_code
    ON public.user_badges(user_id, badge_code) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_user_badges_user_id ON public.user_badges(user_id);
CREATE INDEX IF NOT EXISTS idx_user_badges_expires_at ON public.user_badges(expires_at);
```

- 승인(APPROVED) 시점에 `user_badges`에 `ACTIVE` row upsert, 만료/취소(EXPIRED/REVOKED) 시점에
  같은 row를 상태 전환 (부분 유니크 인덱스 덕분에 "유저당 코드당 활성 뱃지 1개"가 DB 레벨에서 보장됨).
- 이 설계는 **테이블 하나를 추가로 늘리는 결정**이므로 CTO 승인 시 "user_badges 신설에 동의하는지,
  아니면 subscription_verifications 안에서 최신 APPROVED row를 뱃지로 간주하는 단순한 방식을
  원하는지"를 확인해야 한다 (BLOCKER 목록 #3).

### 3.3 `subscription_verification_audit_logs`

기존 `referral_audit_logs`(`migrations/air_0221_referral_stage1_foundation.sql` 167~187행)는
`entity_type CHECK (... IN ('commission','withdrawal'))`로 하드 제약되어 있어 그대로 재사용하려면
CHECK 제약을 변경하는 마이그레이션이 필요하다. **재활용 대신 같은 패턴의 전용 테이블을 새로 둔다**
(추천인 도메인과 감사 성격이 다르고, 제약 변경으로 인한 기존 기능 영향 위험을 피하기 위함).

```sql
CREATE TABLE IF NOT EXISTS public.subscription_verification_audit_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    verification_id  UUID NOT NULL REFERENCES public.subscription_verifications(id) ON DELETE CASCADE,
    action           TEXT NOT NULL CHECK (action IN (
                          'uploaded','analysis_started','auto_approved','sent_to_review',
                          'approved','rejected','revoked','reanalyzed','expired','expiry_date_edited'
                      )),
    actor_id         UUID REFERENCES public.profiles(id) ON DELETE SET NULL,  -- NULL = 시스템/배치
    reason           TEXT,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subverif_audit_verification_id ON public.subscription_verification_audit_logs(verification_id);
CREATE INDEX IF NOT EXISTS idx_subverif_audit_action ON public.subscription_verification_audit_logs(action);
```

### 3.4 트리거

기존 관례(`set_<table>_updated_at()` + `trg_<table>_updated_at`)를 그대로 `subscription_verifications`,
`user_badges`에 적용 (`_APPLY.sql`에 idempotent하게 포함).

---

## 4. Storage 설계

- **버킷명**: `subscription-verifications` (지시사항 제안 그대로 채택, 기존 `videos` 버킷과 별개).
- **Private 버킷** — `storage.buckets.public = false`로 생성. 기존 `videos`(public) 패턴과 정반대이므로
  실수로 public 토글하지 않도록 마이그레이션 CHECKLIST에 명시.
- **경로**: `chatgpt-plus/{user_id}/{verification_id}/original.{ext}` (지시사항 그대로).
  `{ext}`는 서버가 실제 컨텐츠에서 판별한 확장자만 허용 (`.jpg/.jpeg/.png/.webp/.pdf`), 클라이언트가
  보낸 파일명을 신뢰하지 않는다.
- **업로드 경로**: 클라이언트(브라우저/데스크톱 앱)가 Supabase Storage에 직접 쓰지 않는다.
  파일은 신뢰된 서버(§SECURITY #1 결론에 따른 위치)로 멀티파트 업로드 → 서버가 SHA-256/MIME 검증 후
  service_role 키로 Storage에 업로드. (기존 `videos` 버킷의 `createSignedUploadUrl` 클라이언트-직접-업로드
  패턴은 **채택하지 않는다** — 그 라우트 자체가 인증 체크도 없는 참고용 사례였다.)
- **조회 경로**: 원본 URL/Public URL을 절대 DB에 저장하지 않는다. 웹어드민이 증빙을 볼 때만
  서버가 `createSignedUrl(path, expiresIn=300)`(5분 등 짧은 만료)을 그때그때 생성해서 반환.
- **RLS(storage.objects)**: 버킷 전체에 대해 `anon`/`authenticated` INSERT/SELECT 정책을 **만들지 않는다**
  (기존 DB 테이블과 같은 "RLS enabled, 정책 없음 = service_role 전용" 컨벤션). 클라이언트가 직접
  Storage에 접근할 경로 자체가 없으므로 정책 부재가 곧 올바른 기본값이다.

---

## 5. 제안 API 목록

> 위치는 SECURITY §1의 아키텍처 결론에 따라 **auth-web(Next.js, 호스팅 서버)** 을 기본 전제로 하되,
> 데스크톱 앱에서 호출하는 프록시 엔드포인트도 함께 표기한다. CTO가 다른 배치를 택하면 경로만
> 바뀐다.

### 5.1 사용자용 (auth-web, 사용자 본인 Bearer 토큰 인증)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/subscription-verifications` | 증빙 업로드(multipart) + 자동 분석 트리거. `provider`, `document_type_hint`, 파일. |
| GET | `/api/subscription-verifications?provider=chatgpt_plus` | 본인의 최신 인증 상태 + 이력 조회 |
| GET | `/api/subscription-verifications/:id` | 단건 상세 (본인 소유만) |
| POST | `/api/subscription-verifications/:id/resubmit` | 반려/만료 후 갱신 제출 (신규 row 생성) |
| GET | `/api/badges/me` | 현재 보유 뱃지 목록 (`user_badges` ACTIVE) |

### 5.2 데스크톱 앱 프록시 (`app/routers/settings.py` 추가, 세팅 화면에서 호출)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/settings/chatgpt-plus/verify` | 파일을 받아 auth-web `/api/subscription-verifications`로 그대로 전달(프록시). 로컬에서 Gemini 호출/판정 로직 없음. |
| GET | `/api/settings/chatgpt-plus/status` | auth-web의 상태 조회를 프록시 (세팅 화면 표시용) |

### 5.3 웹어드민용 (auth-web `/api/admin/subscription-verifications/*`, `requireAdmin`/`requireSuperAdmin`)

| Method | Path | 설명 | 권한 |
|---|---|---|---|
| GET | `/api/admin/subscription-verifications` | 목록(필터: status/provider/user) | requireAdmin |
| GET | `/api/admin/subscription-verifications/:id` | 상세 + Signed URL + Gemini 분석 결과 | requireAdmin |
| POST | `/api/admin/subscription-verifications/:id/approve` | 승인 → APPROVED, badge 부여 | requireAdmin |
| POST | `/api/admin/subscription-verifications/:id/reject` | 반려(+사유) | requireAdmin |
| POST | `/api/admin/subscription-verifications/:id/revoke` | 인증 취소 → REVOKED, badge 비활성 | requireSuperAdmin (파급력 고려) |
| POST | `/api/admin/subscription-verifications/:id/reanalyze` | Gemini 재분석 | requireAdmin |
| PATCH | `/api/admin/subscription-verifications/:id/expires-at` | 만료일 수동 수정 | requireSuperAdmin |
| GET | `/api/admin/subscription-verifications/:id/audit` | 감사 로그 조회 | requireAdmin |
| GET | `/api/admin/subscription-verifications/signed-url?path=...` | 짧은 만료 Signed URL 발급 | requireAdmin |

### 5.4 내부 배치용

| 트리거 | 대상 | 설명 |
|---|---|---|
| 일일 1회 | `POST /api/internal/subscription-verifications/sweep-expired` (또는 DB 함수 직접) | `expires_at <= now()`인 APPROVED row → EXPIRED, 연결된 `user_badges` → EXPIRED |

---

## 6. 유저 UI 변경 파일 예상 목록 (데스크톱 앱)

- `templates/pages/settings.html` — "외부 서비스 인증 > ChatGPT Plus 인증" 카드 신설 (§1.1 위치)
- `static/js/settings_page.js` — 업로드/상태조회/갱신 제출 JS 함수 추가 (`handleStyleImageSelect` 패턴 재사용)
- `app/routers/settings.py` — §5.2의 프록시 엔드포인트 2개 추가
- `services/i18n.py` — ko/en/vi/th 4블록에 신규 키 추가 (상태 라벨, 안내 문구, 반려 사유 등)
- (신규) `services/subscription_verification_client.py` — auth-web API 호출 래퍼 (기존
  `services/web_admin_client.py`와 같은 결의 파일)

## 7. 웹어드민 변경 파일 예상 목록

- (신규) `auth-web/app/admin/subscription-verifications/layout.tsx` — 탭 네비게이션 (`referrals/layout.tsx` 패턴)
- (신규) `auth-web/app/admin/subscription-verifications/page.tsx` — 목록/필터
- (신규) `auth-web/app/admin/subscription-verifications/[id]/page.tsx` — 상세/승인/반려/재분석/만료일 수정
- (신규) `auth-web/app/admin/subscription-verifications/audit/page.tsx` — 감사 로그
- (신규) `auth-web/app/admin/subscription-verifications/_components.tsx`, `_hooks.ts`, `_shared.ts`
  (`referrals/_shared.ts`의 `getAdmin()`/`parsePagination()` 패턴 재사용)
- (신규) `auth-web/app/api/admin/subscription-verifications/**/route.ts` (§5.3 엔드포인트들)
- (신규) `auth-web/app/api/subscription-verifications/**/route.ts` (§5.1 엔드포인트들)
- `auth-web/components/DashboardContent.tsx` — 회원 관리 리스트 테이블에 "ChatGPT Plus 인증" 컬럼/뱃지
  1줄 표시 + 유효 종료일 (기존 3202~3360행 테이블에 컬럼 추가하는 최소 변경만, 로직은 위 신규
  라우트에서 가져옴)

## 8. 정기 작업(만료 처리) 제안

§1.5 조사에 따라 데스크톱 앱 프로세스 상주 asyncio 루프는 "앱이 꺼져있으면 안 도는" 근본적 한계가
있어 **채택하지 않는다.** 세 가지 대안을 우선순위와 함께 제시하며, auth-web 실제 배포 환경(예:
Vercel 여부) 확인이 필요해 CTO 결정 항목으로 남긴다 (BLOCKER #4):

1. **(권장, 만약 Vercel 배포라면)** Vercel Cron Jobs → `auth-web`의
   `/api/internal/subscription-verifications/sweep-expired`를 매일 1회 호출. 별도 인프라 불필요,
   기존 Next.js 배포에 자연스럽게 포함.
2. **(권장, 배포 플랫폼 무관)** 이미 Windows 릴리즈에 쓰고 있는 GitHub Actions에 `on: schedule: cron:`
   워크플로우를 신설해 위 엔드포인트를 매일 1회 curl로 호출. 저장소에 이미 익숙한 도구이므로
   운영 부담이 적다.
3. **(비권장)** Supabase `pg_cron` — 과거 재참여(re-engagement) 기능에서 명시적으로 기각된 전례
   (`project_handoff/AIR-0205/DUMP.md`)가 있으나, 이번 케이스는 단순 DB UPDATE라 pg_cron이 기술적으론
   더 잘 맞을 수 있음. 다만 이 저장소에 pg_cron 실사용 전례가 전혀 없어 새 운영 부담이 생긴다.

만료 임박 알림(7일/3일/당일)은 위 스윕 배치가 도는 김에 같은 잡에서 조건만 다르게 조회해서
(예: `expires_at BETWEEN now()+6d AND now()+7d`) 이메일/인앱 알림을 큐잉하는 방식을 제안한다.
알림 발송 채널(이메일/인앱)은 기존 알림 인프라 유무를 확인 못 했으므로 BLOCKER 목록에 추가한다.

---

## 9. 단계별 구현 순서 (제안)

1. **Stage 0 (본 문서)** — 설계 승인
2. **Stage 1** — DB 마이그레이션 (`subscription_verifications`, `user_badges`,
   `subscription_verification_audit_logs`, RLS) + Storage 버킷 생성. **여기까지는 배포해도 눈에 보이는
   기능이 없어 안전하게 먼저 반영 가능** (기존 관례상 별도 `_APPLY.sql`/`_rollback.sql`/`_CHECKLIST.md`/`_IMPACT.md`)
3. **Stage 2** — auth-web 사용자용 API(§5.1) + Gemini 분석/규칙 점수 로직 (기능 플래그로 숨김 배포 가능)
4. **Stage 3** — 데스크톱 앱 세팅 화면 업로드 UI + 프록시 엔드포인트(§5.2, §6)
5. **Stage 4** — 웹어드민 관리 화면(§5.3, §7)
6. **Stage 5** — 만료 배치(§8) + 알림
7. **Stage 6** — QA 전체 시나리오 통과 후 정식 오픈 (기능 플래그 해제)

## 10. 기존 기능과의 충돌 가능성

- **낮음.** `profiles`, `referral_audit_logs` 등 기존 테이블을 변경하지 않고 신규 테이블만 추가하므로
  스키마 충돌 없음.
- **마이그레이션 번호 충돌 주의**: 현재 저장소에 커밋된 최신 번호는 `air_0227`이지만, 작업 트리에
  `air_0221c`, `air_0224a` 등 **아직 커밋되지 않은 동시 진행 중인 다른 작업**(추천인 Stage2, AIR-0223,
  AIR-0224)이 있다. 이번 기능의 실제 번호(`air_0228` 가제)는 구현 착수 시점에 다시 확인해야 한다.
- `DashboardContent.tsx`의 회원 리스트 테이블에 컬럼 1개를 추가하는 것은 매우 국소적인 변경이라
  충돌 위험이 낮지만, 이 파일이 4,759줄짜리 단일 컴포넌트라 diff 리뷰 시 주의 필요.
- `services/i18n.py`는 10,997줄짜리 단일 파일이라 동시에 다른 브랜치에서도 키를 추가하고 있다면
  머지 충돌 가능성이 있음 (다른 문제는 아니고 파일 크기에서 오는 통상적 리스크).
