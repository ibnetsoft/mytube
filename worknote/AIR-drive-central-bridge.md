# AIR-drive-bridge — 중앙 Google Drive OAuth 토큰 브릿지

## 배경

유저앱(영상 생성 데스크톱 앱)이 특정 소수 직원이 아니라 불특정 다수(수백 대 규모)에
배포될 계획으로 바뀌면서, 렌더링 파이프라인이 쓰던 `token.pickle`(구글 Drive/YouTube
OAuth refresh_token)을 각 설치본에 두는 방식은 AIR-0225B(`SUPABASE_SERVICE_ROLE_KEY`
공개 유출 사고)와 같은 유형의 위험이 된다. refresh_token은 만료 없이 재사용 가능한
강력한 자격증명이라 어떤 설치 프로그램/로컬 파일에도 포함시켜서는 안 된다.

## 구조

- `auth-web/app/api/desktop-drive-token` (신규): refresh_token을 서버(Vercel)에만
  보관하고, 요청마다 구글 OAuth 서버에서 ~1시간짜리 `drive.file` 스코프 access_token으로
  교환해 돌려준다. 실제 파일 업로드/다운로드는 이 서버를 거치지 않고 클라이언트↔구글
  드라이브 간 직접 통신 — 서버리스 함수의 요청 크기/타임아웃 제한과 무관하게 대용량
  렌더링 결과물을 처리할 수 있다.
- 인증 경로 2가지:
  - 유저앱(다수, 신뢰도 낮은 기기): `email` + `session_token` — `desktop-topics-bridge`와
    동일한 HMAC 세션 메커니즘 재사용.
  - 렌더링 워커(단일, 회사 관리 기기): 이미 로컬에 있는 `SUPABASE_SERVICE_ROLE_KEY`를
    Supabase Auth Admin API(`/auth/v1/admin/users`)에 실시간으로 호출해 검증 — 이
    엔드포인트는 진짜 service_role 키만 호출 가능하므로, 서버 쪽에 같은 비밀의 사본을
    별도로 저장/비교할 필요가 없다(사본이 어긋나는 문제를 원천 차단).
- `services/google_drive_service.py::_get_drive_service()`만 수정 — 로컬 `token.pickle`
  대신 신규 `services/drive_bridge_client.py`를 통해 이 브릿지에서 access_token을 받아
  옴. 업로드/다운로드/폴더생성 등 나머지 로직은 전혀 안 바뀜.

## Git

- PR #89 (`feat/drive-central-bridge`) — 브릿지 신규 + 클라이언트 마이그레이션. main 병합됨.
- PR #90 (`fix/drive-bridge-worker-auth-live-check`) — 프로덕션 실테스트 중 발견: 로컬
  `.env`와 Vercel의 `SUPABASE_SERVICE_ROLE_KEY` 사본이 어긋나 있어 워커 인증이 401로
  실패 → 저장된 값 비교 대신 Supabase Auth Admin API 실시간 검증으로 교체. main 병합됨.

## 검증

- `tokens/token_1.pickle`의 refresh_token을 직접 추출해 구글 OAuth 서버에 refresh
  요청 → 200 확인, `drive.file`/`youtube`/`youtube.upload` 스코프 확인 (회사 공용
  계정 토큰 1개만 존재함을 사용자가 확인).
- 프로덕션 배포 후 실제 호출로 end-to-end 확인:
  - 워커 키로 `/api/desktop-drive-token` 호출 → 200, 실제 access_token 발급.
  - 그 access_token으로 구글 Drive API(`files.list`) 직접 호출 → 200, 기존 렌더링
    파이프라인이 만든 실제 파일들(`metadata.json`, `thumbnail.png`, 렌더링된 mp4,
    프로젝트 폴더) 정상 조회.
  - 잘못된 키 / 인증 정보 누락 → 401 정상 거부.
- 유저앱(email+session_token) 경로는 코드 상 desktop-topics-bridge와 동일한 검증
  함수를 재사용하므로 별도 라이브 테스트 없이도 신뢰 가능하나, 실제 로그인 세션으로
  살려서 테스트하지는 않았다 — 다음에 실제 계정으로 데스크톱 앱을 실행할 때 자연스럽게
  검증될 것.

## 남은 것

- PR #88(`fix/drive-asset-category-folder`, 에셋 업로드 카테고리 폴더)은 내부적으로
  `_get_drive_service()`를 호출하므로 이 브릿지가 있으면 추가 수정 없이 자동으로 같은
  방식을 탄다 — 병합 여부는 사용자 판단 대기 중.
- `remote_drive_worker.py`(렌더링PC)는 이미 로컬에 `SUPABASE_SERVICE_ROLE_KEY`를
  갖고 있어 별도 수정 없이 워커 인증 경로를 그대로 탄다 — `token.pickle`을 렌더링PC에
  복사해둘 필요가 완전히 없어짐(애초에 이 작업의 계기가 된 질문 해결).
