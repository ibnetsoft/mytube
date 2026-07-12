# AIR Worker — Local API 보안 (AIR-0227C Stage 3/10)

- 상태: **구현 + 실측 공격 시나리오 QA 완료**
- 구현: `worker/local_api_token.py`, `worker/local_api_app.py`, `worker/cli_status.py`
- 관련 문서: [SECURITY](./AIR_WORKER_SECURITY.md) (원래 §5 잔여 위험이었던 항목을 여기서 해소)

## 1. 정책

**`/health`만 무인증.** 그 외 모든 엔드포인트(읽기 전용 포함: `/status`, `/processes`,
`/jobs`, `/jobs/{id}`, `/logs`)가 인증을 요구한다. AIR-0227C부터 job payload에
`lease_id`/`worker_instance_id`/`source_path` 같은 정보가 실리기 시작하므로, "읽기 전용이니
민감정보 없음"이라는 가정이 이번 Task부터 더 이상 성립하지 않는다고 판단해 가장 보수적인
기본값(전부 인증)을 택했다.

파괴적 엔드포인트(`/shutdown`, `/processes/*/start|stop`, `/jobs/{id}/cancel`,
`/jobs/submit`, QA 전용 `/_test/crash-local-api`)는 추가로 감사 로그(`[AUDIT]` 접두사,
`local_api.log`에 기록, **토큰 값 자체는 절대 기록 안 함**)를 남긴다.

## 2. 토큰 저장 — DPAPI

`pywin32`가 이미 프로젝트 의존성이라(설치 확인됨) "이번 Task에서 구현이 과도하면 최소한
파일 권한 제한" 조항의 "과도함" 기준을 넘지 않는다고 판단해 **DPAPI를 실제로 구현**했다
(`win32crypt.CryptProtectData`/`CryptUnprotectData`) — Windows 계정에 암호학적으로
묶이므로, 같은 PC의 다른 Windows 계정은 파일을 훔쳐도 복호화할 수 없다. pywin32가 없는
환경(개발/이식성)을 위해 평문+ACL 제한 폴백도 구현했다(`storage_backend()`로 어느 쪽이
활성인지 확인 가능 — 실측: 이 개발 환경에서는 `dpapi`가 활성).

추가로 파일 자체의 Windows ACL도 현재 사용자에게만 `Full Control`로 제한한다
(`icacls /inheritance:r /grant:r`) — DPAPI만으로 충분하지만 이중 방어.

## 3. 요구사항 대비 구현

| 요구사항 | 구현 |
|---|---|
| Authorization 헤더 사용 | ✅ `Bearer <token>`, FastAPI `Header` 의존성 |
| URL query parameter 토큰 금지 | ✅ 어떤 엔드포인트도 query param을 확인하지 않음 - 실측: `?token=whatever`로 시도해도 401 |
| 명령행 인자 토큰 금지 | ✅ `cli_status.py`는 토큰을 인자로 받지 않고 로컬 DPAPI 저장소에서 직접 읽음 |
| 토큰 로그 출력 금지 | ✅ `require_auth`/감사 로그 어디도 헤더 값을 출력하지 않음; `logging_setup.py`의 기존 redaction 필터(AIR-0227B)가 `access_token`류 패턴도 이중으로 걸러냄 |
| 안전한 비교 함수 | ✅ `hmac.compare_digest` |
| 토큰 미제공 → 401 | ✅ |
| 잘못된 토큰 → 일관된 401 | ✅ "missing과 invalid를 구분하지 않는다"로 정책 확정 - 응답에서 두 경우를 구별할 수 있는 정보를 주지 않음(403 대신 401로 통일) |
| 토큰 파일 권한 최소화 | ✅ DPAPI + icacls 이중 |
| 재발급 지원 | ✅ `cli_status.py --reissue-token` |
| 재발급 후 이전 토큰 즉시 무효화 | ✅ 설계상 자동 - 검증이 매 요청마다 디스크에서 현재 토큰을 다시 읽으므로(캐싱 없음) 파일이 덮어써지는 순간 이전 토큰은 즉시 실패 |

## 4. 실측 공격 시나리오 (Stage 10, 전부 라이브로 재현)

| 시나리오 | 결과 |
|---|---|
| `/health` 토큰 없이 | `200` (의도대로 무인증) |
| `/status` 토큰 없이 | `401` |
| `/shutdown` 토큰 없이 | `401`, **실제로 종료되지 않음** 확인(직후 `cli_status.py`로 생존 확인) |
| `/shutdown` 잘못된 토큰 | `401` |
| `/shutdown` URL query로 토큰 전달 시도 (`?token=whatever`) | `401` (query param을 아예 안 읽으므로) |
| 올바른 토큰으로 `/status` | `200` |
| `--reissue-token` 후 이전 토큰으로 재시도 | `401` (즉시 무효화 확인) |
| 재발급 후 CLI(자동 최신 토큰 사용)로 재시도 | `200` |
| 반복 실패 요청 | 429 같은 rate limit은 구현하지 않음(§5 잔여 위험) - 매 시도 로그는 남지만 차단은 없음 |
| 헤더 로그 노출 여부 | uvicorn을 `log_level="warning"`으로 띄워 접근 로그 자체가 안 남고, 애플리케이션 로그도 헤더 원문을 출력하지 않음을 코드 리뷰로 확인 |
| Local API 재시작 후 토큰 유지 | ✅ 토큰은 디스크(DPAPI 파일)에 있으므로 프로세스 재시작과 무관 - `get_or_create_token()`이 기존 파일을 그대로 복호화 |

## 5. 잔여 위험 (정직하게 명시)

- **Rate limiting 없음**: 반복 실패 요청을 막는 lockout/backoff가 없다. 로컬 loopback
  전용이라는 1차 방어선(§SECURITY §2)이 있지만, 같은 PC의 다른 악성 프로세스가 무차별
  대입을 시도하는 것 자체를 막지는 못한다. 토큰이 `secrets.token_urlsafe(32)`(256비트
  엔트로피)라 무차별 대입 자체는 비현실적이지만, 다음 Task에서 실패 횟수 기반 지연을
  검토할 가치가 있다.
- **DPAPI는 Windows 전용**: 리눅스/Mac에 이식할 경우 평문+파일권한 폴백만 남는다 -
  크로스플랫폼 배포 계획이 생기면 재검토 필요.
