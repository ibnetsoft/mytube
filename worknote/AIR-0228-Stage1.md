# AIR-0228 Stage 1 — ChatGPT Plus 구독 인증 뱃지: 스키마 기반 작업

## 날짜
2026-07-15

## 한 일
`docs/CHATGPT_PLUS_VERIFICATION_SPEC.md` §9 Stage 1을 그대로 실행:
- `migrations/air_0228_chatgpt_plus_verification_stage1.sql` (+ `_APPLY.sql`/`_rollback.sql`/
  `_CHECKLIST.md`/`_IMPACT.md`) 작성, `pglast`로 실제 PostgreSQL 문법 검증 통과.
- PR #93으로 main 병합.
- 사용자가 `_APPLY.sql`을 Supabase SQL Editor에서 직접 실행 → "Success. No rows returned" +
  검증 어설션 통과 확인.
- 읽기 전용으로 재확인: `subscription_verifications`/`user_badges`/
  `subscription_verification_audit_logs` 3개 테이블 전부 존재+0건, `subscription-verifications`
  Storage 버킷 존재+Private(`public: false`) 확인.

## 만든 것
- 새 테이블 3개 (전부 비어있음, 어떤 application code도 아직 안 씀)
- Private Storage 버킷 1개
- 기존 테이블/컬럼/애플리케이션 코드는 전혀 안 건드림

## 다음 단계 (미착수)
Stage 2부터: auth-web 사용자용 API + Gemini 구조화 응답 분석 + 규칙 점수 로직.
착수 전에 `docs/CHATGPT_PLUS_VERIFICATION_SECURITY.md` §1의 아키텍처 BLOCKER(승인/판정
로직을 auth-web에서 실행 vs 데스크톱)를 먼저 결정해야 함 - Stage 1 스키마는 어느 쪽이든
마이그레이션 변경 없이 지원 가능하도록 설계됨.
