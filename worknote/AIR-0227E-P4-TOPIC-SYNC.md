# AIR-0227E-P4 — 유저앱 주제 페이지 P0 회귀 조사 및 복구

## Task ID
`AIR-0227E-P4`

## Date
`2026-07-13`

## 상태
**범위 축소 완료 — Conditional Go.** 사용자가 지시한 16단계 중 "9단계: 기존 20개 즉시 복구"에
해당하는 부분만 정식으로 수정했다. Hermes 결과 중앙 저장/웹어드민 카테고리별 화면/카테고리별
20개 유지 정책 등(3~13단계의 나머지)은 이번 세션에서 **착수하지 않았다** — 실제 발견한 문제의
범위(7개 파일이 동일한 service_role 문제를 갖고 있음)를 사용자에게 먼저 알린 뒤,
"user_topics.py만 정식복구"로 범위를 명시적으로 좁히기로 사용자가 직접 선택했다.

브랜치: `feat/air-0227e-p4-topic-central-sync` (base: `main`)

---

## 1. 기존 20개가 사라진 원인 (1~2단계 조사 결과)

**Hermes/AIR-0227E-P3와는 전혀 무관하다.** AIR-0227E-P3는 별도 git worktree
(`LongformGenerator-airworker-p3`)에서만 작업했고 main에 병합된 적이 없다.

- 실 원인은 이보다 하루 전 main에 이미 병합된 **AIR-0225B 보안 수정**
  (commit `83951d8f`, "remove service_role from desktop release pipeline")이다. 이
  커밋은 `SUPABASE_SERVICE_ROLE_KEY`가 공개 GitHub 릴리즈 zip에 평문으로 포함되어
  새고 있던 것을 막기 위해, **패키징된 배포용 데스크톱 앱의 `.env`에 그 키를 더 이상
  넣지 않도록** `windows-release.yml`/`build_windows.ps1`/`AIRStudio.spec`을 고쳤다.
  (이 저장소를 체크아웃한 개발 환경의 로컬 `.env`에는 여전히 그 키가 있어, 소스에서
  직접 실행하면 재현되지 않는다 — 실제 배포된 릴리즈 빌드에서만 나타난다.)
- 그런데 `app/routers/user_topics.py`는 이 보안 수정과 별개로 그 전부터
  `os.getenv("SUPABASE_SERVICE_ROLE_KEY")`를 직접 읽어 Supabase에 접속하고
  있었고, 이 파일은 AIR-0225B 마이그레이션 대상에서 빠졌다 — 그 결과 배포된
  데스크톱 앱에서는 `/api/user/recommended-topics`가 항상 500을 반환하게 됐다.
- 같은 패턴(`SUPABASE_SERVICE_ROLE_KEY` 직접 사용)이 `app/routers/auth.py`,
  `app/routers/settings.py`, `services/dispatcher_service.py`,
  `services/remote_drive_render_service.py`, `services/render_queue_worker.py`,
  `services/web_admin_client.py`에도 있다 — **이번 세션에서는 이 6개 파일을
  건드리지 않았다.** 뒤의 3개는 렌더 서버 쪽(별도 배포 채널일 가능성)이라 지금
  당장 깨졌다고 단정할 근거가 없고, 앞의 3개는 확인/수정 여부를 사용자가 별도로
  판단해야 한다.
- 프론트엔드(`templates/pages/projects.html`)도 문제가 있었다: `loadRecommendedTopics()`가
  `res.ok`나 `data.status`를 확인하지 않고 `data.topics.length > 0`이 아니면 무조건
  "추천 주제 없음" 빈 상태로 빠져, 500 에러와 진짜 빈 상태를 사용자가 구분할 수 없었다.

## 2. 데이터 삭제 여부 (2단계 조사 결과) — 삭제되지 않았음

프로덕션 Supabase에 직접(읽기 전용) 확인:

```
topics_queue 전체: 2,219건
status='pending' (사용 가능): 2,175건
가장 최근 생성: 2026-07-03
```

**즉 데이터는 전혀 사라지지 않았다** — "읽는 통로"(`user_topics.py`의 인증 방식)만
막혀 있었다. 이 발견 덕분에 Hermes로 새로 20개를 생성할 필요 없이, 읽기 경로만
고치면 기존 2,175개가 즉시 다시 보인다.

## 3. 수정 방식 — service_role을 데스크톱에 되살리지 않는 프록시

AIR-0225B가 막은 것을 그대로 되돌리는 대신(`SUPABASE_SERVICE_ROLE_KEY`를 다시 데스크톱
`.env`에 넣는 것), 로그인/세션 재개(`/api/desktop-resync`)가 이미 쓰고 있는 것과
**동일한 인증 방식**(`email` + `session_token`, `lib/desktopSession.ts::
verifyDesktopSessionToken` — HMAC, `DESKTOP_SESSION_SECRET`으로만 서명/검증,
service_role과 무관)을 재사용하는 새 브릿지를 만들었다.

### 3-A. 신규: `auth-web/app/api/desktop-topics-bridge/route.ts`

**화이트리스트된 action만 허용** — 일반적인 "아무 쿼리나 실행" 프록시가 아니다.
탈취된 session_token 하나가 할 수 있는 일은 아래 8개뿐이고, 각각 서버가 스스로
스코프를 강제한다(클라이언트가 이메일/테이블/필드를 임의로 바꿀 수 없음):

| action | 하는 일 | 스코프 강제 |
|---|---|---|
| `get_longform_policy` | `global_settings`에서 longform 정책 4개 키만 조회 | 키 목록을 서버에 하드코딩 — API 키 등 다른 global_settings 값은 이 경로로 절대 못 봄 |
| `get_pending_topics` | `topics_queue` status=pending + categories 조인 | 읽기 전용 |
| `get_cached_recommendations` | `user_topic_recommendations` 캐시 조회 | `employee_email`을 검증된 이메일로 서버가 고정 |
| `save_recommendations` | 추천 캐시 저장 | 각 행의 `employee_email`을 서버가 강제로 덮어씀 |
| `get_profile_prefs` | 본인 프로필의 언어/영상길이/카테고리 선호만 조회 | 이메일 고정 |
| `get_rebalancing_settings` | `payout_rebalancing_settings` 조회 | - |
| `get_boosts` | `category_priority_boosts` 조회 | - |
| `get_stored_translations` / `save_translations` | 번역 캐시 조회/저장 | lang을 en/vi/th로 제한, 저장 시 필드명 화이트리스트 |
| `claim_topic` | resolve+fetch+patch(topics_queue)+patch(recommendations)를 원자적으로 처리 | 이미 assigned된 주제 재요청 시 409, race condition 방지용 `.eq('status','pending')` 조건부 PATCH |

`npx tsc --noEmit` 통과 확인(신규 파일 기준 에러 0건 — 나머지 출력은 이 파일과
무관한 기존 컴포넌트의 사전 존재 타입 에러).

### 3-B. `app/routers/user_topics.py` 수정

- `_supabase_headers()`(직접 service_role 사용) 완전히 제거.
- 신규 `_call_bridge(action, params)` 헬퍼 — `auth_service.get_user_email()` +
  `auth_service.get_session_token()`(신규 getter, `services/auth_service.py`에 3줄 추가)로
  브릿지 호출.
- `_fetch_longform_policy`, `_fetch_stored_translations`, `_save_translations_to_db`,
  `_apply_multipliers_to_topics`, `get_recommended_topics`, `claim_topic` 전부
  브릿지 호출로 교체 — **점수 계산/페이로드 정규화/로컬 프로젝트 생성 등 비즈니스
  로직은 단 한 줄도 바꾸지 않았다**, 오직 "어떻게 Supabase에 접속하는가"만 바뀜.
- `_resolve_claimable_topic_id`는 브릿지의 `claim_topic` action이 서버 쪽에서
  통째로 처리하므로 삭제(중복 로직 제거, 죽은 코드 아님 — 실제로 로직이 이전됨).
- `python -c "import ast; ast.parse(...)"` 로 구문 검증 통과.

### 3-C. `templates/pages/projects.html` 수정

- `res.ok` 확인 후 실패 시 명확한 에러 상태(`recommendedTopicsError` 신규 div) 표시,
  진짜 빈 상태(`recommendedTopicsEmpty`)와 구분.
- `data.status !== 'ok'`인 경우도 동일하게 에러로 처리 — 더 이상 서버 오류가
  "추천 주제 없음"으로 둔갑하지 않는다.
- 4개 언어(`services/i18n.py`: ko/en/vi, th는 원래 이 문자열 자체가 없어 기존과
  동일하게 둠)에 `error_loading_recommendations` 문구 추가.

## 4. 검증 — 정직하게 명시: 실제 계정 기반 살아있는 E2E는 수행하지 못했다

- `npx tsc --noEmit`: 신규 브릿지 파일 타입 에러 0건 확인.
- `python -m ast`: 수정한 두 `.py` 파일 구문 오류 없음 확인.
- 코드 리뷰: 모든 호출 지점(`get_recommended_topics`/`claim_topic`/`_apply_multipliers_to_topics`
  등)이 새 `_call_bridge()` 경로로 정확히 연결되어 있고, `_supabase_headers`/
  `os.getenv("SUPABASE_SERVICE_ROLE_KEY")` 잔여 참조가 없음을 grep으로 재확인.
- **실제 로그인 계정으로 끝까지 살려서 테스트하지는 못했다** — `profiles.id`가
  `auth.users(id)`에 외래키로 걸려 있어 진짜 Supabase Auth 계정 없이는 테스트용
  프로필 행 자체를 만들 수 없었고, 그렇다고 이 세션이 새 인증 계정을 만드는 것은
  허용된 행동 범위 밖이라 판단해 시도하지 않았다. 사용자에게 확인한 결과
  "코드 검토만으로 마무리"를 선택함에 따라, 이 항목은 **미검증으로 정직하게 남겨둔다.**
  실제 계정으로 로그인해 주제 페이지를 열어보는 것이 이 수정의 최종 확인 단계로
  남아 있다.

## 5. 알려진 제한사항 / 다음 단계

- 나머지 6개 파일(`auth.py`, `settings.py`, `dispatcher_service.py`,
  `remote_drive_render_service.py`, `render_queue_worker.py`,
  `web_admin_client.py`)의 동일 문제는 이번에 다루지 않았다 — 실제 배포 빌드에서
  깨져 있는지 여부부터 별도 확인 필요.
- P4 지시사항의 3~13단계(Hermes 결과 중앙 저장, 웹어드민 카테고리별 화면,
  카테고리별 20개 유지 정책, 중복 방지 등)는 사용자의 명시적 선택으로 **착수하지
  않았다** — 별도 세션/작업으로 남겨둠.
- 실제 사용자 계정으로 데스크톱 앱을 열어 주제 페이지가 실제로 20개를 다시
  보여주는지 최종 확인이 필요하다(§4).

## 6. Git

- 브랜치: `feat/air-0227e-p4-topic-central-sync` (base `main`)
- main 병합 없음, production 배포 없음(auth-web의 새 라우트는 push 시 Vercel
  Preview로만 자동 배포됨 - Production은 이 브랜치가 main에 병합되기 전까지 영향 없음).
