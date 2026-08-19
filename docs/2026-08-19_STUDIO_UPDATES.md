# 📢 에어스튜디오 (AIR STUDIO) 일일 업데이트 보고서

- **작성 일자**: 2026년 8월 19일
- **대상 서비스**: `https://studio.airing.work` (웹 스튜디오 & 인증 시스템)
- **주요 목적**: SNS 추천 링크 연동, 8대 카테고리 동기화, 자막 상태 로직 교정, 모바일 반응형 UI 구축, 프로젝트 테이블 UX 고도화

---

## 1. 🔗 SNS 공유용 추천 링크 및 자동 가입 연동
- **추천 링크 자동 생성 및 원클릭 복사**:
  - 설정 및 추천 탭에 `https://studio.airing.work/?ref=추천코드` 전용 링크 인풋과 복사 버튼 추가.
- **URL 파라미터 감지 및 자동 가입 전환**:
  - 상대방이 SNS 추천 링크를 클릭하여 접속하면 URL의 `ref` 파라미터를 자동 인식.
  - 별도 조작 없이 **회원가입 화면이 자동으로 열리고 추천인 코드가 기입**되도록 구현.

---

## 2. 📂 선호 영상 주제 8대 공식 카테고리 동기화
- **공식 8대 카테고리 표준화**:
  1. `옛날이야기` (id: 2)
  2. `경제` (id: 3)
  3. `탈북사연` (id: 4)
  4. `한국사연` (id: 5)
  5. `해외감동` (id: 6)
  6. `무협` (id: 7)
  7. `노후금융` (id: 8)
  8. `황혼19금` (id: 9)
- **전 화면 데이터 일치 및 DB 반영**:
  - 회원가입 시 선택한 카테고리가 기본 설정 화면과 웹 어드민 회원정보에 100% 동일하게 일치.
  - 설정 탭에서 카테고리 수정 후 저장 시 Supabase DB(`profiles`) 및 Auth 메타데이터에 실시간 반영되는 `/api/std/update-profile` API 신설.

---

## 3. 🎬 헤더 자막 스텝 초록불 상태 로직 교정
- **기본 진입 시 회색불 유지**:
  - 프로젝트 로드 시 자막 프리뷰가 자동 생성되어 있더라도, 유저가 검토/저장하지 않은 상태에서는 헤더에 초록불이 켜지지 않도록 처리 (`isSubtitleSaved = false`).
- **파란색 [저장] 버튼 연동**:
  - 자막 툴바 우측 상단의 **파란색 [저장] 버튼**을 클릭했을 때 자막 데이터가 영구 저장되며 상단 헤더의 자막 단계에 초록불(`✓`)이 켜지도록 로직 수정.

---

## 4. 📱 모바일 반응형 UI/UX 레이아웃 최적화 (Mobile-Friendly)
- **랜딩 및 인증 화면 (`/`, `AuthForm`)**:
  - 모바일 패딩 및 여백 최적화로 양옆이 짓눌리던 레이아웃 개선.
  - 모바일 1열 스택 / 태블릿·데스크톱 2열 그리드 적응형 폼 및 터치 친화적 인풋 적용.
- **스튜디오 작업 화면 (`/std`)**:
  - **모바일 햄버거(☰) 메뉴 & 슬라이드 드로어 네비게이션** 탑재 (모바일에서 사이드바가 본문을 가리지 않고 부드럽게 열림).
  - **상단 5단계 스텝퍼 모바일 가로 스크롤 바** 지원.
  - 모바일 화면 패딩(`p-3 sm:p-5 md:p-6`) 및 툴바 줄바꿈(`flex-wrap`) 적용으로 좁은 화면에서도 컨텐츠 영역 최대 확보.

---

## 5. 🎯 프로그레스 스텝 및 제출 조건 최적화
- **[설정] 스텝 완전 제거**:
  - 헤더 상단 스텝퍼와 프로젝트 목록 상태 열에서 영상 제작 흐름과 무관했던 **[설정] 단계를 완전히 제거**.
  - 실제 영상 제작 필수 6개 단계(`기획`, `대본`, `이미지`, `TTS`, `자막`, `썸네일`) 완료 시 제출 가능하도록 조건 통일.

---

## 6. 📊 프로젝트 목록 테이블 UX & 제출 버튼 인터랙션 고도화
- **[프로젝트명] 칼럼 ➡️ [카테고리] 칼럼으로 교체**:
  - 프로젝트명 열을 제거하고 해당 주제가 속한 **공식 8대 카테고리 뱃지 태그**로 렌더링.
- **[제출] 헤더 텍스트 시각적 강조**:
  - 밝은 시안색(`text-cyan-300 font-black`)으로 시인성 강화.
- **엔터 모양(⏎) 제출 버튼 3단계 인터랙션 디자인**:
  1. **미완료 상태 (비활성화)**: 가시성을 살짝 높인 은은한 회색 버튼 (`text-gray-400 bg-white/10`).
  2. **6단계 완료 상태 (제출 대기)**: 밝은 흰색 엔터 아이콘과 블루 글로우 펄스 애니메이션 (`text-white font-black bg-blue-600 ring-2 ring-white/60 animate-pulse`).
  3. **제출 완료 상태**: 원격 렌더 큐에 정상 접수된 경우 선명한 초록색 버튼 (`text-emerald-400 bg-emerald-600/25 border-emerald-500/50`).

---

## 📦 관련 커밋 히스토리
- `48709ff5`: feat: Add referral link auto-fill, sync official 8 categories across signup/settings/admin, and fix subtitle save step status
- `c9712ed7`: feat: Optimize mobile responsive layout, hamburger drawer, and adaptive form styling
- `1783c996`: fix: Remove unnecessary settings step from header stepper and projects list table
- `9bcd8380`: feat: Replace project name with category column, brighten submit header, and add 3-state enter submit button