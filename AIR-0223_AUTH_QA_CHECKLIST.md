# AIR-0223A — Authenticated QA Checklist (CTO 작성용)

이 문서를 채워서 돌려주시면 `AIR-0223_AUTH_QA.md`로 정리하겠습니다.
Access Token/Service Role Key는 사용하지 않았습니다 — 전부 실제 브라우저 로그인 세션으로 진행해 주세요.

---

## 실패 시 확인할 로그 위치 (미리 알아두면 좋음)

| 증상 | 확인 위치 |
|---|---|
| 페이지가 하얗게 뜨거나 콘솔에 빨간 에러 | 브라우저 개발자도구 **Console** 탭 |
| API가 403/500/기타 에러 | 개발자도구 **Network** 탭 → 해당 `/api/admin/referrals/...` 요청 클릭 → **Response** 탭에서 에러 메시지 확인 |
| 로컬(`localhost:3000`)에서 테스트 중이라면 | `npm run dev` 실행 중인 터미널 창의 출력 |
| Vercel 배포본(`mytube-ashy-seven.vercel.app`)에서 테스트 중이라면 | Vercel 대시보드 → 해당 프로젝트 → **Deployments** → 최신 배포 → **Functions** 탭에서 `/api/admin/referrals/*` 함수 로그 |
| 데이터가 이상하게 보임 (있어야 할 게 없다 등) | Supabase 대시보드 → **Logs** → **API Logs** (같은 시간대 요청 확인) |

---

## 클릭 테스트 체크리스트 + 기대 결과

### 1. 진입
- [ ] `ejsh0519@naver.com`으로 로그인 후 `/admin/referrals` 접속
- **기대 결과**: 상단에 "Referral Admin Dashboard" 제목과 탭바가 보이고, 에러 화면 없이 Dashboard 탭(KPI 카드)이 표시됨

### 2. 탭 6개 표시/전환
- [ ] 탭바에 Dashboard / Organization / Commission / Withdrawals / Audit / Settings 6개가 보임
- [ ] 각 탭을 순서대로 클릭
- **기대 결과**: 클릭할 때마다 URL이 `/admin/referrals/...`로 바뀌고, 콘솔 에러 없이 해당 화면이 뜸 (Member Detail은 별도 탭이 아니라 Organization에서 회원 이름 클릭 시 진입하는 상세 페이지입니다)

### 3. API 응답 코드
- [ ] 개발자도구 Network 탭을 열어둔 채로 각 탭을 한 번씩 방문
- **기대 결과**: `/api/admin/referrals/dashboard`, `/organization`, `/commissions`, `/withdrawals`, `/audit` 요청이 모두 **200** (403이면 실패 — 로그인 세션이 안 잡힌 것)

### 4. 검색/필터/페이지네이션
- [ ] Organization 탭: 검색창에 아무 글자나 입력 → Country 필드에 "KR" 입력 → 날짜 필터 지정 → 활동여부 드롭다운 변경 → Tree/Table 버튼 전환
- [ ] Commission 탭: Level 드롭다운, 날짜, 회원검색 입력
- [ ] Withdrawals 탭: Status 드롭다운, 날짜, 회원검색 입력
- [ ] Audit 탭: Type/Action 드롭다운, 회원/관리자 검색, 날짜 필터
- **기대 결과**: 데이터가 없으므로 전부 "No data found." 정도의 빈 화면만 뜨면 정상 (에러 메시지나 콘솔 에러가 뜨면 실패). 페이지네이션 컨트롤은 데이터가 1페이지 미만이면 아예 안 보이는 게 정상입니다.

### 5. CSV Export
- [ ] Commission 탭의 "Export CSV (current page)" 버튼 확인
- **기대 결과**: 데이터가 없으므로 버튼이 **비활성화(회색, 클릭 안 됨)** 상태인 게 정상입니다. 혹시 나중에 테스트 데이터가 생기면, 버튼 클릭 시 `.csv` 파일이 다운로드되는지 재확인 부탁드립니다.

### 6. Country Manager 지정
- [ ] Settings 탭 하단 "Country Manager" 섹션에서 **테스트용 User ID**(실제 서비스 계정이 아닌, 영향받아도 괜찮은 계정)를 넣고 Country Code 입력 후 "Assign as Country Manager" 클릭
- **기대 결과**: 초록색 "Assigned as Country Manager." 메시지가 뜸. ⚠️ 이건 실제로 해당 계정의 `app_metadata.role`을 `sub_admin`으로 바꾸는 진짜 동작입니다 — 테스트 후 되돌리려면 별도 확인이 필요합니다(문서 하단 "Country Manager 해제 불가" 항목 참고).

### 7. Withdrawal 승인/거절 버튼
- [ ] Withdrawals 탭에서 목록에 항목이 있는지만 확인 (없으면 이 항목은 "데이터 없어 확인 불가"로 기록)
- **주의**: **테스트 데이터가 없으면 Approve/Reject 버튼을 절대 클릭하지 마세요.** 실제로 상태를 바꾸는 동작입니다.
- **기대 결과**: 데이터가 있다면 REQUESTED/APPROVED/SENDING 상태의 행에만 Approve/Reject 버튼이 보이고, COMPLETED/REJECTED 행에는 안 보임

### 8. Audit 목록
- [ ] Audit 탭 진입
- **기대 결과**: 빈 목록("No data found.")이 에러 없이 표시됨

### 9. Settings 링크 이동
- [ ] Settings 탭에서 "Open Referral Settings →" 버튼 클릭
- **기대 결과**: 기존 `/admin/settings/referral` 페이지(Referral Mode/Level%/Default Sponsor 등)로 정상 이동

### 10. 기존 admin 메뉴 회귀 확인
- [ ] 기존에 쓰시던 다른 admin 화면(메인 대시보드, `/admin/settlements`, 기존 `/admin/settings/referral` 등)을 한 번씩 열어봄
- **기대 결과**: 이번 변경 이전과 동일하게 동작함 (새로 깨진 화면이 없어야 함)

---

## PASS/FAIL 기록 양식

| # | 항목 | PASS/FAIL | 비고 (에러 메시지, 스크린샷 등) |
|---|---|---|---|
| 1 | 진입 | | |
| 2 | 탭 6개 표시/전환 | | |
| 3 | API 응답 200 | | |
| 4 | 검색/필터/페이지네이션 | | |
| 5 | CSV Export | | |
| 6 | Country Manager 지정 | | |
| 7 | Withdrawal 버튼 표시 | | |
| 8 | Audit 목록 표시 | | |
| 9 | Settings 링크 이동 | | |
| 10 | 기존 메뉴 회귀 없음 | | |

**전달 방법**: 위 표를 채워서(또는 각 항목별 스크린샷/메모와 함께) 보내주시면, 결과를 받아 `AIR-0223_AUTH_QA.md`에 PASS/FAIL 표 + 발견된 UI/API 문제 목록 + 기존 빌드 이슈(별도로 이미 확인된 `settlements/page.tsx` 등 3건)와의 구분을 명시해 정리하겠습니다.
