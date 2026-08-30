# 에어스튜디오 일일 업데이트 보고서

- 작성 일자: 2026년 8월 30일
- 대상 모듈: `auth-web` STD TTS, 관리자 Dashboard, 관리자 전역 설정 저장 API
- 주요 목적: ElevenLabs 음성 생성 복구, 생성 오디오/원본 대본 복구, `/dashboard` 관리자 진입 안정화, 비밀키 저장 유실 방지

---

## 1. STD TTS 복구 및 보관 강화

### 1-1. 생성 오디오 새로고침 복구
- STD 프로젝트 복원 시 `audio` 자산도 함께 복구하도록 수정했습니다.
- 생성된 TTS 오디오를 로컬 지정 폴더와 프로젝트 자산 상태에 함께 반영하도록 보강했습니다.
- 새로고침 또는 프로젝트 재진입 시 `audioResultUrl`을 다시 복원하도록 변경했습니다.

### 1-2. 워커 원본 대본 복구 버튼 추가
- TTS 편집기 상단에 `워커 원본 대본 복구` 버튼을 추가했습니다.
- 프로젝트 payload에 `original_worker_script`를 같이 저장하고, 기존 토픽 데이터의 `pregenerated_script`까지 fallback으로 탐색하도록 했습니다.
- 복구 버튼 실행 시 원본 대본 복원 후 씬/자막 전체 동기화까지 한 번에 수행되게 했습니다.

### 1-3. ElevenLabs 서버 생성 경로 보강
- `sys_api_elevenlabs`, `sys_api_elevenlabs_keys`, 환경변수 `ELEVENLABS_API_KEY`, `ELEVENLABS_API_KEYS`를 순차적으로 읽도록 유지하되, 마스킹 문자열/빈 문자열은 실제 키로 취급하지 않도록 필터링했습니다.
- ElevenLabs 생성 시 모델을 하나로 고정하지 않고 `eleven_v3 -> eleven_multilingual_v2` 순서로 fallback 가능하게 보강했습니다.
- 선택한 voice가 유효하지 않을 경우 기본 voice ID로 재시도하도록 보강했습니다.

---

## 2. 관리자 Dashboard 진입 안정화

### 2-1. `/dashboard`에서 `/std`로 튕기던 흐름 수정
- 관리자 세션이 없거나 권한 판정이 어긋날 때 `/`로 보내던 로직을 제거했습니다.
- 루트 `/`가 `/std`로 리다이렉트되기 때문에, 기존 구조에서는 `/dashboard` 접근 시 직원 로그인 화면으로 튕길 수 있었습니다.
- 이제 `/dashboard` 자체에서 관리자 로그인 UI를 직접 렌더링합니다.

### 2-2. 관리자 권한 판정 완화
- `user.email === SUPER_ADMIN_EMAIL` 단일 비교에서, 소문자 정규화 비교와 `app_metadata.is_superadmin`, `user_metadata.is_superadmin`, `role === sub_admin`까지 함께 보도록 확장했습니다.
- 비관리자 사용자는 자동으로 `/std`로 보내지 않고, 현재 화면에서 다른 계정으로 다시 로그인할 수 있게 변경했습니다.

---

## 3. 관리자 설정 저장 안정화

### 3-1. 저장 실패 메시지 노출
- 관리자 전역 설정 저장 실패 시 프론트에서 조용히 무시하던 동작을 제거했습니다.
- 이제 `/api/admin/settings/global` 실패 응답이 오면 즉시 alert로 원인을 노출합니다.

### 3-2. 비밀키 유실 방지
- 전역 설정 저장 API에서 `gemini`, `youtube`, `youtube_keys`, `claude`, `elevenlabs`, `elevenlabs_keys`, `topview`, `suno`를 비밀값으로 취급합니다.
- `••••`, `***`, `(미설정)`, 빈 문자열, `undefined`, `null` 같은 값은 기존 저장값을 덮어쓰지 않도록 변경했습니다.
- `elevenlabs_keys`도 전역 설정 저장 대상 목록에 포함되도록 정리했습니다.

---

## 4. 검증 결과

### 4-1. 테스트/정적 검사
- `venv\Scripts\python.exe -m pytest tests\test_std_tts_persistence.py -q`
  - 결과: `3 passed`
- `auth-web` ESLint
  - 신규 에러 없음
  - 기존 hook dependency / `img` warning만 남음

### 4-2. 브라우저 실검증
- `2026-08-30` 기준 배포된 `https://studio.airing.work/std?tab=tts` 화면에서 ElevenLabs `음성 생성`을 직접 실행했습니다.
- 결과:
  - `음성 생성 중...` 진입 확인
  - `생성 완료된 음성 오디오` 섹션 표시 확인
  - 오디오 태그 생성 확인
- 추가 관찰:
  - 브라우저 자동화 환경에서는 `showDirectoryPicker`가 사용자 제스처로 인정되지 않아 로컬 폴더 저장 경고가 남을 수 있음
  - 이 경고는 ElevenLabs 생성 실패가 아니라 로컬 폴더 피커 제약에 해당함

### 4-3. 로컬 `.env` 키 검증
- 로컬 `.env`의 `ELEVENLABS_API_KEY`로 ElevenLabs `voices` API를 직접 조회했을 때는 `invalid_api_key`가 반환됐습니다.
- 즉 로컬 키는 무효였고, 실제 배포 환경/DB 저장 키와는 별개로 관리되고 있을 가능성이 있습니다.

---

## 5. 금일 관련 커밋

### 로컬 작업 커밋
- `ed6f236` Fix STD TTS restore and worker recovery
- `61870df` Fix admin dashboard auth flow and STD ElevenLabs fallback
- `49774eb` Fix admin settings save feedback and preserve secret keys

### 원격 `main` 반영 커밋
- `2e34ac6` Fix STD TTS restore and worker recovery
- `a9b3b20` Fix admin dashboard auth flow and STD ElevenLabs fallback
- `fb93edf` Fix admin settings save feedback and preserve secret keys

---

## 6. 주요 변경 파일

- `auth-web/app/std/page.tsx`
- `auth-web/lib/stdLocalMedia.ts`
- `auth-web/app/api/std/tts-key/route.ts`
- `auth-web/app/api/std/projects/[projectId]/tts/generate/route.ts`
- `auth-web/components/DashboardContent.tsx`
- `auth-web/app/api/admin/settings/global/route.ts`
- `tests/test_std_tts_persistence.py`

---

## 7. 잔여 메모

- 현재 메인 작업트리에는 TTS/관리자 수정과 무관한 미해결 merge 상태 파일이 별도로 남아 있습니다.
- 오늘 푸시는 충돌 확산을 피하기 위해 별도 clean worktree에서 필요한 커밋만 cherry-pick해서 `origin/main`에 반영했습니다.

---

## 8. ElevenLabs API 키 운영 기준

### 8-1. 관리자 입력 위치와 최대 개수
- 관리자 페이지의 `APIKEY & 시스템 설정 > AI 핵심`에서 설정합니다.
- `ElevenLabs API Key`에는 기본 키 1개를 입력합니다.
- `ElevenLabs Backup API Keys`에는 쉼표 또는 줄바꿈으로 백업 키를 최대 3개 입력합니다.
- 런타임에서 사용하는 키는 기본 1개와 백업 3개를 합쳐 최대 4개입니다. 중복, 빈 값, 마스킹 문자열은 제외하며 4개를 초과한 키는 사용하지 않습니다.
- 실제 키 값은 소스, 문서, 브라우저 로그에 기록하지 않습니다.

### 8-2. 저장 키와 적용 우선순위
- 기본 키는 Supabase `global_settings.sys_api_elevenlabs`에 저장됩니다.
- 백업 키 목록은 Supabase `global_settings.sys_api_elevenlabs_keys`에 저장됩니다.
- 관리자 DB에 사용 가능한 키가 하나라도 있으면 관리자 DB 키만 사용합니다. 이 경우 Vercel 환경변수의 오래된 키를 풀에 섞지 않습니다.
- 관리자 DB에 키가 전혀 없을 때만 `ELEVENLABS_API_KEY`, `ELEVENLABS_API_KEYS` 환경변수를 fallback으로 사용합니다.
- STD 음성 생성, 성우 목록 조회, TTS 키 조회 API는 `auth-web/lib/elevenLabsKeys.ts`의 공통 로더를 사용합니다.

### 8-3. 백업 키 전환과 성우 권한
- 기본 키에서 잔액 소진, 쿼터 초과, 결제 제한, 인증 실패 또는 성우 접근 제한이 발생하면 다음 백업 키를 순서대로 시도합니다.
- 키가 정상이어도 ElevenLabs 계정의 플랜, 워크스페이스 또는 성우 공유 상태가 다르면 선택한 Professional/Private Voice를 사용할 수 없습니다.
- 백업 계정이 선택한 성우를 사용할 수 없을 때는 해당 계정에서 사용 가능한 기본 premade 성우로 재시도합니다.
- 일관된 음색이 필수라면 등록한 네 계정 모두에서 같은 성우를 사용할 수 있는지 먼저 확인해야 합니다.

### 8-4. 운영 점검 절차
1. 관리자 페이지에서 기본 키와 필요한 백업 키를 저장합니다.
2. 페이지를 새로고침한 뒤 입력란이 마스킹 상태로 유지되는지 확인합니다.
3. STD TTS 화면에서 성우 목록을 다시 불러오고 짧은 대본으로 생성을 시험합니다.
4. 실패 alert의 ElevenLabs 상태 코드와 메시지로 쿼터, 인증, 성우 권한 문제를 구분합니다.
5. 장문 생성 전에는 등록된 키 전체의 남은 크레딧이 대본 분량을 감당하는지 확인합니다.

### 8-5. 관련 반영 커밋
- `dc9e0d5` Use admin ElevenLabs keys across STD

---

## 9. Google Drive 공통 OAuth 관리자 설정

### 9-1. 관리자 입력 항목
- `APIKEY & 시스템 설정 > Google Drive` 탭에서 OAuth Client ID, Client Secret, Refresh Token, Root Folder ID를 관리합니다.
- 요청된 운영 방식에 따라 네 값은 관리자 화면에서 마스킹하지 않고 평문으로 표시합니다.
- 해당 탭과 설정 API는 시스템 설정 권한이 있는 관리자만 접근할 수 있습니다.

### 9-2. 적용 범위와 우선순위
- 관리자 DB의 `sys_api_google_drive_*` 값이 완전하게 설정돼 있으면 Vercel 환경변수보다 우선합니다.
- 관리자 OAuth 값이 하나도 없을 때만 기존 `GOOGLE_DRIVE_*` 환경변수를 fallback으로 사용합니다.
- OAuth 세 값 중 일부만 저장된 경우 서로 다른 계정 정보가 섞이지 않도록 Drive 작업을 중단합니다.
- 웹 STD 에셋 업로드·제출·TTS 보관, 관리자 Drive 파일 수정, 데스크톱 앱과 원격 렌더 워커의 중앙 토큰 브리지가 같은 설정을 사용합니다.

### 9-3. 워커 보안 구조
- 장기 Refresh Token을 워커 PC로 전달하지 않습니다.
- 워커는 `/api/desktop-drive-token`에서 단기 Access Token과 Root Folder ID를 받아 Drive에 접근합니다.
- 새 Root Folder ID는 기존 원격 렌더 폴더 설정보다 우선해 워커 런타임에 반영됩니다.

### 9-4. 제출 및 워커 폴더 검증
- 기존 프로젝트에 과거 Drive 폴더 ID가 남아 있어도 현재 Root Folder의 자식인지 API로 검증한 후 재사용합니다.
- 현재 Root 밖의 기존 폴더는 새 업로드에 재사용하지 않고 현재 Root 아래에 프로젝트·에셋 폴더를 다시 준비합니다.
- 원격 워커는 각 작업 시작 전에 관리자 Root Folder 설정을 다시 불러옵니다.
- 제출 API 오류를 성공으로 표시하던 UI fallback을 제거하고 실제 실패 원인을 사용자에게 표시합니다.
- 기존 완료 큐의 파일은 자동 이동하지 않으며, 워커는 저장된 Drive File ID로 계속 조회할 수 있습니다.
