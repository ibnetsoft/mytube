# ChatGPT Plus 구독 인증 뱃지 시스템 — 테스트 계획 (QA)

- 상태: **설계안 / 구현 착수 전** — 아래 항목들은 각 Stage 구현 시 실행할 테스트의 사전 설계다.
- 관련 문서: [SPEC](./CHATGPT_PLUS_VERIFICATION_SPEC.md), [SECURITY](./CHATGPT_PLUS_VERIFICATION_SECURITY.md)

---

## 1. 단위 테스트

### 1.1 규칙 기반 채점 엔진
- 필수 날짜(payment_date/next_renewal_date/billing_period_end) 전부 존재 + confidence 높음 + tampering_risk=low
  → 95점 이상 → APPROVED 판정 로직이 정확히 threshold 경계(94.99 vs 95.00)에서 분기하는지.
- 필수 날짜 전부 없음 → 점수 무관하게 자동승인 금지 → NEEDS_REVIEW.
- `duplicate_image_flag=true` → 점수가 100이어도 NEEDS_REVIEW (자동승인 안 됨) 확인.
- `visual_tampering_risk in (medium, high)` → 자동승인 금지 확인.
- `required_fields_visible=false` → 자동승인 금지 확인.

### 1.2 유효기간(expires_at) 계산
- `next_renewal_date` 존재 → `expires_at = next_renewal_date + 7일` 정확히 계산되는지 (월말/연말 경계,
  윤년 2/29 포함).
- `next_renewal_date` 없고 `payment_date` 존재 → `expires_at = payment_date + 37일`.
- 둘 다 없음 → `expires_at = NULL`, 상태가 강제로 `NEEDS_REVIEW`(관리자 검토)로 가는지.
- `EXPIRING` 파생 상태: `status='APPROVED' AND expires_at BETWEEN now() AND now()+7d` 쿼리가
  정확히 7일 경계에서 포함/제외되는지 (off-by-one 확인).

### 1.3 파일 검증
- 확장자는 `.jpg`인데 실제 콘텐츠가 SVG/HTML/실행파일인 경우 매직바이트 검사에서 거부되는지.
- 정상 PDF/JPG/PNG/WEBP 각각 통과하는지.
- 10MB 초과 파일 거부, 10MB 정확히 경계값 처리.
- 빈 파일(0바이트), 파일명에 경로 조작 문자열(`../../etc/passwd`) 포함 시 안전하게 처리되는지.
- SHA-256 계산 결과가 알려진 테스트 파일의 알려진 해시값과 일치하는지 (골든 값 대조).

### 1.4 이메일 마스킹/해시
- `test@example.com` → 마스킹 규칙 적용 결과가 기대값과 일치 (`te***@example.com` 등 실제 채택할
  마스킹 규칙 확정 후 골든 테스트).
- 대소문자/공백이 다른 같은 이메일(`Test@Example.com ` vs `test@example.com`)의 해시가 동일하게
  나오는지 (정규화 로직 검증).

---

## 2. 통합 테스트 (auth-web API, 실제 Supabase 테스트 프로젝트 또는 트랜잭션 롤백 방식)

- `POST /api/subscription-verifications` — 정상 업로드 시 `UPLOADED` row 생성 → 비동기(또는 동기)로
  `ANALYZING`을 거쳐 최종 상태로 전이하는지, `subscription_verification_audit_logs`에 각 단계가
  기록되는지.
- 타인의 verification id로 `GET /api/subscription-verifications/:id` 호출 시 RLS에 의해
  404/403 (다른 사람 것은 안 보임) 확인 — **본인 소유가 아닌 row 접근 차단**이 이번 기능의 핵심
  보안 요구사항이므로 반드시 자동화 테스트로 고정.
- 관리자 API 인증 테스트: `Authorization` 헤더 없이 `/api/admin/subscription-verifications` 호출 →
  401/403. 일반 사용자 토큰으로 호출 → 403. 서브어드민 토큰으로 `approve`/`reject`는 성공하되
  `revoke`/`expires-at` 수정은 403 (requireSuperAdmin 구분 확인).
- 승인(`approve`) API 호출 후 `user_badges`에 `ACTIVE` row가 정확히 1개만 생성되는지(중복 승인
  재호출 시에도 유니크 인덱스로 1개 유지되는지).
- 반려(`reject`) 후 `resubmit` API 호출 시 새 row가 생성되고 이전 row는 `REJECTED`로 그대로 남는지
  (덮어쓰기 되지 않는지).
- 만료 스윕 배치(§SPEC 8)를 수동 트리거해서 `expires_at` 지난 APPROVED row가 EXPIRED로,
  연결된 `user_badges`가 EXPIRED로 함께 바뀌는지, 감사 로그에 `actor_id=NULL`로 기록되는지.
- Signed URL 발급 API가 실제로 짧은 만료(예: 300초)로 발급되는지, 만료 이후 URL 접근 시 실패하는지.

---

## 3. 보안 회귀 테스트 (SECURITY.md 항목별 1:1 대응)

| SECURITY 항목 | 테스트 |
|---|---|
| §1 실행 위치 | 데스크톱 앱 코드베이스(`app/routers/settings.py` 신규 엔드포인트, `services/subscription_verification_client.py`)에 Gemini API 키, service_role 키, 판정 threshold 상수가 **전혀 없음**을 grep 기반 정적 검사로 CI에 고정 (예: 신규 파일에 `SERVICE_ROLE`, `genai.configure`, `95` 임계값 리터럴이 없는지) |
| §2 RLS | 익명/타 사용자 토큰으로 `subscription_verifications` UPDATE 시도 → 실패 확인 (SQL 직접 테스트 또는 API 레벨) |
| §3 관리자 인증 | 위 통합 테스트 참고 |
| §4 개인정보 최소화 | 업로드 응답/DB row 어디에도 마스킹 전 원문 이메일이 노출되지 않는지 필드 단위 검사 |
| §5 파일 업로드 | 위 1.3 |
| §6 사기 탐지 | 동일 파일을 다른 두 테스트 계정으로 업로드 → 두 번째 계정 것이 `duplicate_image_flag=true` + NEEDS_REVIEW로 강제되는지 |
| §7 감사 로그 | 모든 상태 전이 API 호출 후 대응하는 audit log row 존재 확인 |
| §8 서비스 키 노출 | 신규 추가되는 모든 `.tsx`(`"use client"`) 파일과 `static/js/**`, `templates/**`에 `SERVICE_ROLE` 문자열 grep 0건 |

---

## 4. 수동 QA 시나리오 (유저 UI)

1. 정상 플로우: 세팅 > 일반 설정 > 외부 서비스 인증에서 JPG 스크린샷 업로드 → "분석 중" 표시 →
   최종 상태(APPROVED/NEEDS_REVIEW/REJECTED) 반영 → 승인 시 뱃지 표시.
2. 반려 후 갱신: 반려된 상태에서 "갱신 제출" 버튼으로 새 파일 업로드 → 반려 사유가 이전 값으로
   남아있지 않고 새 제출로 초기화되는지.
3. 만료 임박: `expires_at`을 인위적으로 6일 뒤로 설정한 테스트 데이터에서 "만료 예정 안내"
   문구가 뜨는지, 만료 당일 지나면 안내가 "만료됨"으로 바뀌는지.
4. 파일 형식 오류: PDF가 아닌 텍스트 파일 확장자만 `.pdf`로 바꿔서 업로드 → 명확한 에러 메시지
   (원인/해결법 포함), 서버 500이 아닌 사용자 친화적 4xx 응답인지.
5. 용량 초과: 11MB 파일 업로드 → 업로드 전 클라이언트 단에서부터 막히는지, 우회해서 서버로
   보내도 서버가 재검증하는지 (클라이언트 검증 우회 테스트).
6. 다국어: ko/en/vi/th 4개 언어 전환 후 새로 추가된 모든 문구(상태 라벨, 안내, 반려 사유 표시,
   버튼)가 깨지지 않고 번역되는지 — 특히 `services/i18n.py`의 인라인 삼항 안티패턴을 새로
   만들지 않았는지 코드리뷰로 확인.

## 5. 수동 QA 시나리오 (웹어드민)

1. 사용자 목록에서 승인된 계정에 뱃지가 표시되는지, 유효 종료일이 맞는지.
2. 만료된 계정에서 뱃지가 목록에서 사라지는지(활성 뱃지만 표시, 이력은 상세에서 별도 확인 가능해야 함).
3. 상세 화면에서 Signed URL로 원본 이미지가 실제로 열리는지, 5분 후 재요청 없이 같은 링크로
   재접근 시 실패하는지.
4. 승인/반려/재분석/취소/만료일 수정 버튼이 각각 의도한 API를 호출하고 화면이 낙관적 업데이트
   없이(또는 있이) 정확한 최종 상태를 반영하는지.
5. 감사 로그 탭에서 위 모든 액션이 시간순으로 기록되고, 각 액션의 `actor`(관리자 이메일 또는
   "시스템")가 정확히 표기되는지.
6. 서브어드민 계정으로 로그인해 "인증 취소"/"만료일 수정" 버튼이 비활성화(또는 403 처리)되는지.

## 6. 레거시/호환성 테스트

- 기존 회원(뱃지 신청 이력 없는 계정)의 `GET /api/badges/me` 호출 시 빈 배열/정상 404가 아니라
  깨끗한 "미인증" 상태를 반환하는지 (기존 대량의 `profiles` row에 신규 관련 컬럼이 없어도 에러
  없이 동작해야 함 — 이번 기능이 `profiles` 테이블 자체를 변경하지 않으므로 리스크는 낮지만
  확인 필요).
- 기존 회원 관리 리스트(`DashboardContent.tsx`)에 신규 컬럼 추가 후, 뱃지 데이터가 없는
  압도적 다수의 기존 계정에서 컬럼이 빈 값/기본값으로 깨지지 않고 렌더링되는지 (n+1 쿼리 성능
  이슈도 함께 확인 — 사용자 수가 많을 경우 목록 API가 뱃지 조회를 join/batch로 처리하는지).

## 7. 회귀 테스트 (기존 자동화 스위트)

기존 39~57개 회귀 테스트(`tests/test_script_style_*.py`, `tests/test_autopilot_pipeline.py`,
`tests/test_project_music_integration.py` 등)는 이번 기능과 겹치는 영역이 없어 직접 영향은 없을
것으로 예상되나, `app/routers/settings.py`/`services/i18n.py`처럼 여러 기능이 공유하는 파일을
수정하므로 **구현 완료 후 반드시 전체 스위트 재실행**해서 회귀가 없는지 확인한다.

## 8. 배포 전 최종 체크리스트

- [ ] 마이그레이션 `_CHECKLIST.md`의 사전 조건(백업, 트랜잭션 방식) 완료
- [ ] Storage 버킷이 실제로 `public=false`로 생성됐는지 Supabase 대시보드에서 육안 확인
- [ ] `auth-web` 배포 환경에 `SUPABASE_SERVICE_ROLE_KEY`가 정상 설정되어 있는지 (SECURITY §8)
- [ ] 신규 API 라우트 전체에 `requireAdmin`/`requireSuperAdmin` 적용 여부 코드리뷰 체크
- [ ] 데스크톱 앱 신규 코드에 Gemini 키/판정 로직/service_role 키가 없는지 정적 검사 통과
- [ ] 만료 스윕 배치가 최소 1회 실제 스테이징 환경에서 정상 동작 확인
- [ ] 기능 플래그로 우선 비공개 배포 → QA 계정으로 전체 시나리오(§4, §5) 통과 후 공개
