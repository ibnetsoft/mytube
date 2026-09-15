# AIR-0227F — PIN 및 데스크톱 인증체계 개선 (설계, 미구현)

- 상태: **설계 문서만 — 코드 미구현.** 로그인 흐름은 전체 사용자에게 영향을 주는 시스템이고,
  이 세션엔 staging DB/실 Supabase 접속이 없어 마이그레이션·로그인 재작성을 안전하게
  테스트할 방법이 없다. 잘못 구현하면 전체 사용자가 로그인 불가능해질 수 있는 변경이라,
  이번 라운드는 분석 + 설계 + 마이그레이션 계획까지만 진행하고 실 구현은 CTO 승인과
  staging 검증 이후로 미룬다.
- 관련 문서: [SECURITY](./AIR_WORKER_SECURITY.md) §6(관리자 API 핫픽스),
  PR [#73](https://github.com/ibnetsoft/mytube/pull/73)(병합됨 - PIN 원문 응답 제거까지만
  포함, 저장 형식 자체는 이 문서가 다루는 후속 과제)

## 5-1. 현행 인증 흐름 (코드 기준 재구성)

```
[회원가입]
  (auth-web 회원가입 라우트는 이번 조사에서 직접 추적하지 않음 - Supabase Auth의
   기본 가입 플로우로 추정, profiles.pin_code는 가입 시점에 설정되지 않는 것으로 보임
   - 아래 desktop-login의 fallback '1234'가 이를 방증)

[데스크톱 앱 최초 로그인 - services/auth_service.py -> POST /api/desktop-login]
  1. 데스크톱 앱이 email + password(=PIN) 전송
  2. auth-web: profiles.pin_code 조회, 없으면 '1234'로 간주
  3. 평문 비교: dbPassword !== inputPassword -> 401
  4. 통과 시 HMAC 서명 세션 토큰 발급(desktopSession.ts) + 프로필 스냅샷 반환
  5. 데스크톱 앱: 세션 토큰을 쿠키에 저장(다음부터 desktop-resync로 재사용)

[PIN 변경 - POST /api/desktop-change-password]
  1. email + current_password + new_password 전송
  2. profiles.pin_code 평문 비교로 current_password 검증
  3. 통과 시 profiles.pin_code = new_password (평문 그대로 UPDATE)

[라이선스/기기 검증 - services/auth_service.py -> POST /api/verify]
  1. 데스크톱 앱이 매 세션 시작 시(및 주기적으로) userId + hwid(get_hwid(), Windows
     UUID/MAC 폴백) 전송 - 이 호출에는 desktop-login의 세션 토큰이 전혀 실리지 않는다
  2. auth-web: userId로 auth.users + profiles 조회, banned/restricted 확인,
     is_approved 확인
  3. approved_hwid/device_hwid vs incoming hwid 비교 - **단, 이 두 컬럼에 값을
     쓰는 코드가 auth-web/Python 어디에도 없다(전수 grep 확인)** - 즉 이 검사는
     현재 사실상 항상 registeredHwid=''로 스킵되어 never fires. HWID 바인딩은
     설계만 있고 활성화된 적이 없는 것으로 보인다.
  4. 통과 시 profile 스냅샷 + api_keys(개인 키 + 공용 시스템 키 병합) 반환

[프로필 갱신 - POST /api/user/update-profile]
  - userId를 body로 받아 user_metadata 병합 (세션 토큰 검증 없음, §6.2 QA에서
    이미 확인된 trust-the-body 패턴과 동일 계열이나 이번 조사 범위에서 심층 분석은
    하지 않음)

[로그아웃]
  - 이번 조사에서 전용 로그아웃 API를 찾지 못함 - 데스크톱 앱이 로컬에서 세션
    쿠키/토큰을 지우는 것으로 추정(코드 미확인, 후속 조사 필요)
```

**핵심 결론: 세션(desktop-login이 발급한 HMAC 토큰)과 verify(라이선스/기기 검증)가
완전히 분리된 두 개의 신뢰 경로다.** 세션 토큰은 verify 호출에 전혀 실리지 않고,
verify는 `userId`(+사실상 죽은 `hwid` 검사)만으로 완결된다. 이것이 hotfix PR에서 발견한
"bare userId로 인증 성공" 문제의 근본 원인이다 - HWID 검사가 우회 가능한 게 아니라,
**애초에 어떤 실 데이터와도 비교되지 않는 죽은 코드**다.

## 5-2. 즉시 금지 사항 대조

| 금지 항목 | 현재 상태 |
|---|---|
| 신규 계정 기본 PIN 1234 | **여전히 존재** - `dbPassword = String(pinRow.pin_code \|\| '1234')` (desktop-login, desktop-change-password, verify 3곳 전부) |
| PIN 미설정 시 1234 fallback 비교 | **여전히 존재**, 위와 동일 |
| PIN 평문 조회 API | hotfix PR #73으로 admin API 쪽은 제거됨(§SECURITY.md §6.2). desktop-login/verify가 PIN "값 자체"를 반환하진 않지만 "비교"에 평문을 그대로 씀 |
| PIN 평문 로그 | 코드 리뷰 상 발견 안 됨(로그인 성공/실패 로그에 값 자체는 안 찍음) - 재확인 필요 |
| bare userId 인증 성공 | **여전히 존재** - `/api/verify`가 세션 토큰 없이 userId만으로 성공 |
| HWID 누락 시 통과 | **여전히 존재** - 위 §5-1 참고, 사실상 hwid 검사 자체가 비활성 상태 |

## 5-3. PIN 해시 설계 (제안, 미구현)

- **알고리즘**: Argon2id 우선(`argon2-cffi`, Vercel Node 런타임에서 네이티브 바인딩
  이슈 가능성 있음 - Next.js 서버리스 함수에서 argon2 네이티브 모듈이 콜드스타트 시
  문제없이 로드되는지 이 세션에서 검증 불가, 문제 시 `bcryptjs`(순수 JS, 검증된
  대안)로 폴백).
- 사용자별 salt는 알고리즘이 자동 처리(Argon2/bcrypt 둘 다 salt 내장 방식).
- 서버 pepper: 별도 환경변수(`PIN_PEPPER`)로 해시 입력에 추가 - DB가 통째로 유출돼도
  pepper 없이는 크래킹 불가하게. `DESKTOP_SESSION_SECRET`과 같은 급의 비밀로 취급.
- DB: `profiles.pin_hash TEXT` 신설, 기존 `profiles.pin_code`는 **마이그레이션
  완료 전까지 새 코드에서 읽기만 하고 쓰지 않음**(구버전 앱과의 과도기 호환), 완료
  후 컬럼 자체를 드롭(별도 후속 migration, 이번 문서 범위 밖).
- 관리자 API는 이미 hotfix로 `pin_configured: boolean`만 반환하도록 고쳐져 있음 -
  해시 전환 후에도 그대로 유지(원문이든 해시든 어차피 반환 안 함).
- PIN 변경 시: 기존 PIN 해시 검증(`argon2.verify(newHash, currentPin)` 형태) 후
  교체 - "현재 비밀번호 확인 후 변경" 원칙은 그대로 유지.
- **PIN 재설정은 로그인이 아니라 별도의, 이메일 소유를 증명하는 절차로 분리**(§5-4).

### 4자리 PIN 유지 여부

작업 지시서가 요구한 검토: 4자리 숫자는 전수조사(bruteforce) 공간이 10,000가지뿐이라
rate limit 없이는 해시 여부와 무관하게 취약하다. **권장: 최소 6자리 이상으로 상향**,
숫자 전용이어도 6자리면 100만 조합 - rate limit(§5-5)과 결합하면 실질적으로 방어
가능한 수준. 기존 `desktop-change-password`의 신규 비밀번호 정책
(`PASSWORD_PATTERN`: 8자 이상 대소문자·숫자·특수문자)이 이미 있으므로, **PIN이라는
용어 자체를 재검토** - 이미 강한 비밀번호 정책이 있는 변경 경로와, "PIN"이라는 이름의
약한 초기값 경로가 공존하는 것 자체가 혼란의 근원으로 보인다. 제품 요구사항(데스크톱
앱이 4자리 숫자패드 UX를 실제로 요구하는지)은 이 세션에서 확인 불가 - CTO 확인 필요.

## 5-4. 기존 사용자 마이그레이션 (제안, 미구현)

**권장안 채택: 전면 무효화 + 재설정 유도**(작업 지시서의 권장안과 일치):

1. 마이그레이션 시점에 `profiles.pin_hash`를 전부 NULL로 시작(신규 컬럼이므로 자동으로
   NULL).
2. 로그인 시 `pin_hash IS NULL`이면 "PIN이 설정되지 않았습니다 - 이메일 인증 후 새
   PIN을 설정하세요" 흐름으로 분기(로그인 실패가 아니라 재설정 유도).
3. 재설정은 이메일로 발송한 1회용 링크/코드로 본인 확인 후에만 진행(현재 유효 세션이
   있는 사용자는 세션으로 대체 가능).
4. **기존 평문 PIN을 그대로 해시해서 자동 이전하는 방식은 채택하지 않는다** - 이미
   노출됐을 수 있는 값(이번 hotfix의 조사 대상 그 자체)을 해시 형태로만 바꿔봤자
   "유출된 값이 계속 유효한 자격증명으로 남는" 문제를 전혀 해결하지 못한다. 무효화가
   유일하게 정직한 방법.
5. 평문 컬럼 드롭 전 체크리스트: DB 백업 + rollback 스크립트, API 원문 반환 0건(hotfix로
   이미 충족), 로그 포함 0건(재확인 필요), 구버전 데스크톱 앱이 아직 평문 비교 코드를
   쓰고 있다면 강제 업데이트 유도 후에만 드롭.

## 5-5. Rate Limit / 잠금 (제안, 미구현)

- 사용자별: 실패 5회 → 지수 백오프(1분→2분→4분...), 실패 10회 → 15분 임시 잠금.
- IP별: 별도 카운터(계정 순회 공격 방어) - 다만 auth-web이 Vercel 서버리스라 IP별
  상태를 어디에 저장할지 결정 필요(Supabase 테이블에 시도 기록 + RPC로 원자적 카운트,
  또는 Vercel Edge Config/KV - 이 세션에서 어느 쪽이 프로젝트에 이미 있는지 확인 안 됨).
- 성공 시 카운트 리셋, 로그인 시도 자체를 감사 로그에 남김(§7과 연동).

## 5-6/5-7. `/api/verify` 재설계 + HWID 정책 (제안, 미구현)

**근본 방향 전환**: HWID를 "비밀번호 대체 인증 수단"으로 쓰지 않는다(작업 지시서
5-7의 명시적 원칙과, §5-1에서 확인한 "HWID가 애초에 비활성"이라는 사실이 정확히
일치한다 - 지금 이 순간에도 verify는 사실상 "userId만 알면 통과"였다).

제안하는 새 흐름:

```
1. desktop-login이 발급하는 세션 토큰(desktopSession.ts, 이미 HMAC 서명 존재)을
   /api/verify 호출에도 필수로 요구한다 - Authorization 헤더 또는 body의
   session_token 필드. 토큰 없거나 검증 실패 -> 즉시 401, userId만으로는 절대
   통과 못 하게.
2. hwid는 "몇 대까지 허용할지"를 결정하는 부가 정보로 격하 - 인증 자체는 세션
   토큰이 담당, hwid는 "새 기기 최초 사용 시 알림/승인" 같은 UX 신호로만 쓴다.
3. 미등록 hwid(현재 승인된 기기 목록에 없는 새 값)를 만나면: 거부하지 않고,
   별도 승인 큐에 기록 + 관리자 또는 본인 이메일 확인 절차로 승인(즉시 차단은 정상
   사용자의 "새 컴퓨터로 로그인"을 막아 UX를 해칠 수 있음 - 다만 이 판단은 제품
   정책 결정이 필요, 이 세션에서 최종 결정하지 않는다).
4. replay 방지: session_token에 짧은 만료(desktopSession.ts 현재 30일 - verify처럼
   자주 불리는 엔드포인트엔 너무 김, 별도의 short-lived access token 발급을 검토).
5. 토큰 폐기: 비밀번호(PIN) 변경, 명시적 로그아웃, 의심스러운 활동 발견 시 기존
   토큰 전부 무효화 - 현재 desktopSession.ts는 서버가 아무 상태도 저장하지 않는
   순수 서명 검증이라 "폐기"가 불가능한 구조(만료까지 기다리는 수밖에 없음) - 최소
   토큰 발급 시각을 profiles에 기록해두고 "이 시각 이전 토큰은 전부 무효" 같은
   coarse-grained 폐기라도 넣는 걸 권장.
```

## 5-8. API 키 정책

이미 hotfix PR #73에서 관리자 API 응답은 `{configured, last_four}`로 전환 완료
(§SECURITY.md §6.2). 남은 항목(이번 문서 범위, 미구현):
- 서버 내부 복호화만 허용(현재는 `user_metadata`에 평문 저장 - Supabase Auth의
  `user_metadata`/`app_metadata`는 그 자체로 암호화 저장소가 아니므로, 진짜
  암호화하려면 별도 컬럼 + 애플리케이션 레벨 암호화가 필요 - 이번 세션에서 실제
  암호화 계층까지는 설계하지 않았다, 후속 세부설계 필요).
- 키 사용/변경 감사 로그는 §7 후속 Task로 통합.

## 5-9. QA 계획 (구현 후 실행할 목록, 이번 세션에서 실행하지 않음)

기본 PIN 1234 로그인 불가 / PIN 미설정 사용자 자동 로그인 불가 / 정상 새 PIN 설정 /
잘못된 PIN 거부 / 대량 시도 rate limit 발동 / 잠금 및 자동 해제 / PIN 원문이 DB
컬럼·API 응답·로그 어디에도 없음 / bare userId verify 거부 / 세션 토큰 없는 verify
거부 / HWID 누락 시에도 세션 토큰이 유효하면 정상 동작(HWID는 더 이상 유일한 방어선이
아니므로) / 잘못된 세션 토큰 거부 / 토큰 만료 후 거부 / 토큰 재사용(replay) 방어 /
기기 변경 시나리오(새 hwid 승인 흐름) / 기존 데스크톱 앱과의 호환성(구버전이 세션
토큰 없이 verify를 호출하면 어떻게 되는지 - 즉시 차단할지 유예기간을 둘지 결정 필요) /
구버전 차단 시 사용자에게 업데이트 안내가 뜨는지.

**전부 staging 환경(실 Supabase + 실 데스크톱 앱 빌드)에서만 검증 가능 - 이번
세션은 계획만 제공한다.**
