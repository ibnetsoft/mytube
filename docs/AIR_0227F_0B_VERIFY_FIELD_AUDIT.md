# AIR-0227F-0B Stage 1/3 — `/api/verify` 응답 필드 전수조사 + 시스템 키 사용처

## Stage 1. 현재(P0 hotfix 반영 후) 응답 필드 분류

| 필드 | 분류 | 비고 |
|---|---|---|
| `success` | 공개 가능 | 불리언 상태값 |
| `membership` | 인증 사용자에게만 | 플랜(std/pro) |
| `email` | 사용자 본인에게만 | PII |
| `full_name`/`nationality`/`contact` | 사용자 본인에게만 | PII |
| `youtube_channel`/`youtube_handle` | 사용자 본인에게만 | 연동 계정 식별자(준PII) |
| `token_balance` | 인증 사용자에게만 | 과금 정보 |
| `api_keys` (개인 키) | **유효 세션 토큰 보유자에게만 원문**(이번 Stage 2로 전환), 그 외엔 `{}` | 사용자 본인 소유 키 - 상세는 아래 |
| ~~`pin_code`~~ | (이미 제거됨) | AIR-0227D-SECURITY-HOTFIX에서 제거 |
| ~~`sys_api_*`(플랫폼 시스템 키)~~ | (이미 제거됨) | AIR-0227F-0에서 무조건 제거 |

**데스크톱에 전달 금지 / 서버 전용 비밀정보 / 관리자 설정 / 내부 URL**: 이 엔드포인트 응답 어디에도 없음(전수조사 결과, 관리자 설정·내부 인프라 URL·서버 전용 시크릿 필드는 처음부터 포함된 적이 없음 - 문제였던 건 플랫폼 시스템 키와 개인 키의 "무인증 노출"이었지 새로운 카테고리의 필드 노출은 아니었음).

## Stage 2. 개인 API 키 처리 (구현 완료)

- `Authorization: Bearer <유효 토큰>` 없음 → `api_keys: {}` (원문 0건, 크래시 없음 - `Config.load_remote_keys({})`는 빈 dict에 대해 안전하게 no-op).
- 유효 토큰 + `token subject`(토큰에 서명된 이메일) == 조회 대상 `userId`의 이메일 → 기존과 동일하게 원문 반환(호환성을 위한 한시적 예외, 폐기 계획은 Stage 9).
- 토큰이 왔는데 검증 실패(변조/이메일 불일치/만료) → 401, 원문 0건.
- 다른 사용자의 userId 요청: 토큰의 서명 대상 이메일과 요청 userId의 이메일이 다르면 `verifyDesktopSessionToken`이 실패하므로 자동으로 거부됨(상태코드는 401 - 작업 지시서가 제안한 403과는 다르지만 동일하게 "거부"로 귀결, 의미상 "인증 실패"가 "권한 없음"보다 정확하다고 판단해 유지).

## Stage 3. `global_settings` 시스템 키 사용처 조사

| 키 | 데스크톱 사용 위치(코드) | 기능 | 대체 서버 API | BYOK 지원 | 제거 영향 | 긴급 우회 |
|---|---|---|---|---|---|---|
| `GEMINI_API_KEY` | `services/gemini_service.py`, `gemini_music_service.py`, `video_builder_service.py`, `app/routers/image.py`, `app/services/voice_analyzer.py` 등 다수 | 대본/이미지프롬프트/음악기획 등 핵심 AI 생성 전반 | 없음(직접 Gemini API 호출) | `user_metadata.gemini_api_key`로 개인 키 오버라이드 이미 지원 | 없으면 std 등급 사용자의 AI 생성 기능 대부분 정지 | PRO 유저는 원래도 시스템 키를 안 씀(본인 키 필요), std는 영향 큼 |
| `YOUTUBE_API_KEY` | `services/autopilot_service.py`, `app/routers/youtube.py`, `app/routers/gemini.py` | 채널/영상 메타데이터 조회(업로드 자체는 별도 OAuth 흐름으로 추정, 이번 조사에서 미확인) | 없음 | 개인 키 오버라이드 지원 | 메타데이터 조회 기능 저하 | - |
| `ELEVENLABS_API_KEY` | `services/elevenlabs_music_service.py`, `tts_service.py`, `app/routers/tts.py`, `app/routers/music.py` | TTS(음성 합성) | 없음 | 개인 키 오버라이드 지원 | TTS 정지 | - |
| `TOPVIEW_API_KEY`/`TOPVIEW_UID` | `services/topview_service.py` | (기능 상세는 이번 조사 범위 밖 - 서비스명 기준 영상/트렌드 분석 추정) | 없음 | 개인 키 오버라이드 지원 | 해당 기능 정지 | - |
| `CLAUDE_API_KEY` | `services/claude_service.py` | 대본/스크립트 생성(Gemini 대안) | 없음 | 개인 키(`claude_api_key`) 오버라이드 지원(verify.ts keyMap에 있음) | 해당 기능 정지 | - |

**호출 빈도**: 이번 조사에서 각 서비스 파일 내부의 실제 호출 트리거(사용자 액션당 1회 vs 배치)까지는 추적하지 않았다 - 필요 시 후속 조사.

**"BYOK 지원 여부"에 대한 중요한 발견**: 5개 키 전부 이미 `user_metadata.*_api_key`를 통한 개인 키 오버라이드 코드 경로가 `/api/verify`에 존재한다(`keyMap` 참고) - 즉 **BYOK(Bring Your Own Key) 인프라는 이미 대부분 만들어져 있다.** Stage 9("플랫폼 공용 키 클라이언트 전달 폐기")의 실질적 작업량은 "새로 만들기"가 아니라 "std 등급 사용자에게 개인 키 입력을 요구하는 쪽으로 전환하거나, 시스템 키 호출 자체를 서버 프록시로 옮기는 것" 중 하나를 고르는 결정과, 시스템 키 사용 기능(A안: 서버 프록시)에 대해서는 실제로 auth-web에 프록시 엔드포인트를 새로 만들어야 한다.

---

## AIR-0227F-0C 갱신: Stage 8 상태 정정 + 잔존 감사

### 정정된 실제 상태

- **TopView**: 기존 API 키 입력 이력 없음 → 이번 회전 대상에서 제외됨(사용자 확인).
- **Gemini/YouTube/ElevenLabs/Claude**(사용 중인 것): 사용자가 각 공급사에서 **직접 새 키를
  발급**해 **웹어드민의 사용자 개인 키 영역**(`user_metadata.*_api_key`, 즉 위 표의 "BYOK
  오버라이드" 경로)에 저장 완료. 값은 이 문서를 포함해 어디에도 기록하지 않는다.
- 즉 회전은 "시스템 키(`global_settings.sys_api_*`)를 새 값으로 교체"가 아니라 "사용자
  개인 키 슬롯에 새 키를 채워 넣어 그쪽을 쓰게 한다"는 방식으로 이뤄졌다 - `/api/verify`가
  이제 `hasValidToken`일 때만 개인 키를 반환하므로(Stage 2), 세션 토큰을 보내는 클라이언트
  기준으로는 이 개인 키가 우선 사용된다.

### 잔존 감사 결과 (값 미출력, 이름·존재여부·필요조치만)

| 위치 | 확인 방법 | 결과 |
|---|---|---|
| GitHub Actions Secrets (`ibnetsoft/mytube`) | `gh secret list` | `NEXT_PUBLIC_SUPABASE_URL`, `RELEASES_REPO_TOKEN`, `SMTP_FROM/HOST/PASS/PORT/USER` 만 존재. **Gemini/YouTube/ElevenLabs/TopView/Claude 키는 GitHub Secrets에 없음** — 애초에 이 경로로 저장된 적이 없어 삭제 불필요. |
| GitHub Actions Secrets (`ibnetsoft/AIR-releases`) | `gh secret list` | 없음(release 전용 저장소, 정상). |
| 소스코드/문서/테스트 fixture | 하드코딩 키 패턴(`AIzaSy...`, `sk-ant-...`, `sk-...`) 전체 grep | **0건.** |
| 이번 세션 빌드 산출물(`app/.env`) | 스테이징 디렉토리 확인 | **파일 자체가 생성되지 않음** — 로컬 환경변수(`NEXT_PUBLIC_SUPABASE_URL`, `SMTP_*`)가 이 세션에 없어 `build_windows.ps1`의 조건부 write가 스킵됨. Gemini 등 공급사 키는 애초에 이 스크립트가 패키징하는 대상이 아님(오직 Supabase URL + SMTP만 - 아래 별도 발견 참고). |
| production `global_settings.sys_api_*` (Supabase 테이블) | 확인 불가 | **이 세션은 DB 조회 권한이 없다.** 코드상 이 값을 지우는 로직이 어디에도 실행된 적이 없으므로, 예전(유출 가능성이 있던 시점의) 값이 여전히 테이블에 남아있을 가능성이 높다고 가정해야 한다 — **팀에서 직접 Supabase 대시보드로 `global_settings` 테이블의 `sys_api_gemini/youtube/elevenlabs/topview/topview_uid/claude` 행을 확인·삭제 또는 새 값으로 교체 권장.** |
| Vercel production 환경변수 | 확인 불가 | 대시보드 접근 권한 없음 — 애초에 이 5개 키가 Vercel 환경변수로 존재하는지 자체가 불확실(코드상 `global_settings` DB 테이블에서 읽지 Vercel env var에서 읽지 않음 - `auth-web/app/api/verify/route.ts`(과거 버전)와 `auth-web/lib/desktopSession.ts`의 `SYS_KEY_MAP` 참고). 팀에서 실제 Vercel 프로젝트 설정 확인 권장(있다면 무관한 값일 가능성 높으나 확인 필요). |

### 별도로 발견한, 훨씬 심각한 기존 사고 (이번 조사 범위 밖, 교차 참조만)

`.github/workflows/windows-release.yml`과 `worknote/AIR-0225B-*` 문서를 읽던 중,
**`SUPABASE_SERVICE_ROLE_KEY`(Gemini 등 개별 API 키보다 훨씬 강력한, RLS를 완전히 우회하는
마스터 키)가 2026-07-11까지 Windows 빌드에 주입되어 `v2.0.8`~`v2.3.5`(19개 공개 릴리즈)의
`app/.env`에 평문으로 포함되어 있었다**는 사실을 확인했다. 이 문제는:
- `worknote/AIR-0225B-stage0-service-role-removal-investigation.md`에 이미 상세 조사됨(전날,
  다른 세션).
- 영향받은 19개 릴리즈 자산은 `worknote/AIR-0225B-affected-release-inventory.md` 기록에 따라
  이미 **삭제 완료**(2026-07-11).
- GitHub Secrets에서 `SUPABASE_SERVICE_ROLE_KEY` 자체도 삭제됨(이번 세션의 `gh secret list`
  결과에 없음으로 재확인).
- **단, 실제 Supabase `service_role` 키 값 자체가 재발급(rotate)됐는지는 그 조사 문서에서도
  "CTO 결정 대기"로 남아있었다** — 이 세션은 이 부분을 확인할 권한도 방법도 없다.
  **팀에서 AIR-0225B 후속 조치(Phase 0: 실제 키 재발급)가 완료됐는지 별도로 반드시 확인
  필요** — Gemini 키 회전보다 훨씬 우선순위가 높은 항목이다.

## Stage 9 실행 계획 (감사만, 미실행)

작업 지시서 요구 컬럼 그대로, 시스템 키 5종:

| 키 | 서버(auth-web) 현재 사용 여부 | BYOK 오버라이드 경로 | BYOK 미설정 시 현재 동작 | 제거 시 영향 | 제거에 필요한 코드 변경 | production 잔존 여부 | 권장 삭제 순서 |
|---|---|---|---|---|---|---|---|
| `sys_api_gemini` | `/api/verify`에서는 이미 미사용(제거됨). `desktop-login`/`desktop-resync`(`global_settings` 필드)는 여전히 사용 중 | `user_metadata.gemini_api_key` | 개인 키 없으면 AI 생성 기능 전반 정지(가장 광범위 영향) | std 등급 사용자 다수가 이 키에 의존 - 즉시 전면 제거는 사용자 영향 큼 | auth-web에 Gemini 호출 프록시 라우트 신설 필요(A안), 또는 std 등급도 개인 키 필수화 UX 변경(B안) | **확인 불가**(§잔존감사) | 5개 중 **가장 나중** - 영향 범위가 제일 넓음, 서버 프록시(A안) 완성 후 전환 |
| `sys_api_youtube` | 동일 패턴 | `user_metadata.youtube_api_key` | 메타데이터 조회 기능 저하 | 상대적으로 제한적 기능(조회성) | 위와 동일 | 확인 불가 | 중간 |
| `sys_api_elevenlabs` | 동일 패턴 | `user_metadata.elevenlabs_api_key` | TTS 정지 | TTS 사용자에 국한 | 위와 동일 | 확인 불가 | 중간 |
| `sys_api_topview` | 동일 패턴 | `user_metadata.topview_api_key`/`topview_uid` | 해당 기능 정지 | **이번에 확인된 대로 애초에 사용 이력 없음** — 실질적 위험/영향 최소 | 위와 동일(다만 우선순위 낮음) | 확인 불가하나 사용 이력 자체가 없어 저위험 | **가장 먼저 삭제 가능한 후보** - 사용자 영향이 없다고 이미 확인됨 |
| `sys_api_claude` | 동일 패턴 | `user_metadata.claude_api_key` | 스크립트 생성 대안 기능 정지 | Gemini의 대체 경로라 Gemini 정상 시 상대적으로 영향 작음 | 위와 동일 | 확인 불가 | Topview 다음으로 이른 후보 |

**권장 실행 순서(설계만, 미실행)**: ① Topview 먼저 삭제(영향 없음 확인됨) → ② Claude →
③ ElevenLabs/YouTube(사용자 영향 확인 후) → ④ Gemini(서버 프록시 또는 std 등급 BYOK 강제화
완성 후, 가장 마지막). 각 단계마다 삭제 전 해당 키에 의존하는 실사용자 비율을 먼저 파악 권장
(이 세션은 그 데이터에 접근할 수 없음).
