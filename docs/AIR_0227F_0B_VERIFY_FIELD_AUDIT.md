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
