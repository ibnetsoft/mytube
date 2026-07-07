# 05_test_report.md

## AIR-0157F Test Execution Report

| Test Case | Description | Result | Notes |
|---|---|---|---|
| 1 | 일반 유저 Admin API 접근 차단 | PASS | requireAdmin 및 requireSuperAdmin 가드로 403 반환 확인 |
| 2 | Admin 사용자 접근 허용 | PASS | JWT 토큰 검증 후 정상 JSON 응답 반환 |
| 3 | Summary API 정상 | PASS | 전체, 이달, 금일, 레벨별 합계 정상 집계 |
| 4 | Commission List Pagination 정상 | PASS | limit 및 offset 적용 정상, 최신순 정렬 보장 |
| 5 | Filters 정상 | PASS | status, referral_level, user_ids 쿼리 정상 작동 |
| 6 | Commission Detail metadata snapshot 정상 | PASS | 특정 ID 기반 metadata JSONB 객체 파싱 및 반환 성공 |
| 7 | Settings 조회 정상 | PASS | global_settings 테이블에서 요율 기본값(10, 5) 읽기 성공 |
| 8 | Settings 수정 정상 | PASS | SuperAdmin 권한으로 upsert 성공 |
| 9 | 0 미만 / 100 초과 요율 차단 | PASS | PATCH payload 검증 로직으로 차단 확인 (400 Bad Request) |
| 10 | 기존 Commission metadata snapshot 불변 | PASS | Settings 업데이트가 기존 commissions 테이블에 영향 없음 확인 |
| 11 | DashboardContent 탭 렌더링 정상 | PASS | activeTab === 'referral-commissions' 조건 렌더링 정상 |
| 12 | AdminCommissionPanel 분리 렌더링 정상 | PASS | 컴포넌트 프롭스(isAdmin, adminFetch) 바인딩 및 독립 렌더 정상 |
