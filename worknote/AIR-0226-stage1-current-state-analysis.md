# AIR-0226 — Stage 1: 현행 A단계(주제) 흐름 분석 보고서

## Task ID
`AIR-0226-Stage1`

## Date
`2026-07-12`

## 상태
조사 완료. 코드 변경 없음.

---

## 가장 중요한 발견 (설계 전체를 좌우함)

**"주제 생성"은 사용자별 실시간 AI 호출이 아니다.** STD 사용자가 보는 "AI 추천 주제"는
**관리자(웹어드민)가 미리 채워둔 공용 큐(`topics_queue`)에서 스코어링·필터링된 슬라이스**이다.
사용자가 무언가를 클릭하는 순간 AI가 그 사람을 위해 새로 주제를 만들어내는 경로는
**존재하지 않는다.** 이 사실이 Hermes 통합 설계 전체의 전제를 바꾼다 — Hermes는 "사용자 요청 시
실시간으로 대체 호출되는 것"이 아니라, **이 공용 큐를 채우는 파이프라인에 지능을 더하는 것**으로
설계해야 자연스럽다 (design 문서 §아키텍처에서 이 결론을 그대로 반영함).

또한 지시사항이 전제한 "기존 ai_router 기반 주제 생성"은 **STD 흐름에는 존재하지 않는다.**
현재 큐를 채우는 AI 호출은 전부 `auth-web`(Next.js, TypeScript)의
`lib/aiRouter.ts::generateJsonWithModelSetting()`에서 일어나며, Python 쪽 `services/ai_router.py`는
주제 생성에 전혀 관여하지 않는다(뒤에서 설명하는 `TOPIC_GENERATION_MODEL`은 죽은 값). Hermes
실패 시 폴백할 "ai_router"는 새로 정의해야 하는 대상이다 — 자세한 내용은 §7.

---

## 1. 프론트엔드

**실제 큐-claim UI는 `templates/pages/projects.html`이다** (`topic.html`이 아님 — `topic.html`은
유튜브 트렌드 영상 검색·분석 도구로 전혀 다른 기능).

- `GET /projects`(기본 `view=topics`)가 앱의 랜딩 페이지(`/`가 여기로 리다이렉트, `app/routers/pages.py:70-83`).
- 마크업: `projects.html:6-44` — 길이/언어 필터, 새로고침, `#recommendedTopicsGrid` 카드 그리드.
- 전부 인라인 JS (`projects.html` 내부, 별도 `topic.js` 없음):
  - `loadRecommendedTopics()`(`:906-961`) → `GET /api/user/recommended-topics`
  - `applyRecommendedFilters()`(`:963-985`) — 클라이언트 사이드 필터
  - `queueRecommendedTopicTranslations()`(`:999-1038`) → `POST /api/user/recommended-topics/translations`
  - `showTopicConfirm()`/`confirmTopicClaim()`(`:1129-1160`) — 확인 모달 → `claimAndCreateProject()`(`:1164-1214`) → `POST /api/user/claim-topic` → 성공 시 `/script-plan?project_id=...&auto=true&topic=...`로 리다이렉트
  - 레거시 `fetchDailyTopic()`(`:861-900`) → `POST /api/topics/get-daily` — UI 버튼은 숨김(`hidden`) 처리돼 있지만 백엔드 라우트는 살아있음
- STD 등급은 "새 프로젝트"(수동 생성) 버튼 자체가 숨겨짐(`projects.html:97-101`, `templates/base.html:121-124`) — **STD는 claim-큐 경로(또는 관리자 사전배정 경로)로만 프로젝트를 만들 수 있다.**
- 스크린샷에서 본 "TREND MARKET 🇰🇷🇯🇵🇺🇸" 버튼과 주제 텍스트박스/길이/스타일 드롭다운은 사실 **Stage B**(`script_plan.html:144-241`)에 있는 것이고, TREND MARKET 버튼은 `pointer-events:none`으로 **비활성** 상태 — 그냥 "이 프로젝트에 이미 배정된 시장/언어"를 보여주는 읽기 전용 표시일 뿐이다.

## 2. API 라우터 → 서비스 → AI 호출 체인

### 2a. 추천 주제 조회 (Python 앱 내 AI 호출 없음)
`GET /api/user/recommended-topics` → `get_recommended_topics()`(`app/routers/user_topics.py:551-713`):
1. 이메일 인증 → 관리자 정책(`_fetch_longform_policy`) 조회
2. **캐시 우선**: `refresh=false`면 `user_topic_recommendations`(사용자별 캐시 테이블)에서 안 만료된 미claim 행을 그대로 반환 — AI 호출 없음
3. 아니면 회원 프로필(선호 언어/길이/카테고리) 조회 후 `topics_queue`에서 `status=pending` 행을 `categories`와 조인해 가져옴
4. `_calculate_topic_score()`(`:901-953`)로 순수 산술 스코어링(언어일치 +30, 길이일치 +25, 카테고리일치 +20, "나에게 배정됨" +50, "24시간 이내 생성" +10) — **여기 어디에도 LLM 호출 없음**
5. `category_priority_boosts`로 배율 적용, 상위 N개를 `user_topic_recommendations`에 7일 캐시로 저장 후 반환

번역만 유일하게 실시간 모델을 호출할 수 있다: `POST /api/user/recommended-topics/translations`는 먼저
`topics_queue.topic_{lang}` 저장값을 찾고(DB 우선), 없으면 구글 번역 스크레이핑 → 그래도 없으면
`services.ai_router.detect_provider()`로 Gemini/Claude 호출(마지막 수단).

### 2b. 주제 claim → 프로젝트 생성 (역시 AI 호출 없음)
`POST /api/user/claim-topic` → `claim_topic()`(`user_topics.py:759-898`): `topics_queue` 행을
`status='assigned'`로 PATCH하고, `db.create_project()` + `db.update_project_setting()`으로 SQLite에
복사, `user_topic_recommendations.is_claimed=true` 마킹. 순수 데이터 이동, AI 없음.

`POST /api/topics/get-daily` → `get_daily_topic()`(`app/routers/auth.py:~725-840`) — 관리자가 이미
`assigned_employee_email`을 채워둔 행 하나를 가져오는 더 단순한 자매 경로. 역시 AI 없음.

### 2c. 실제로 `topics_queue`를 채우는 AI 호출 위치
**`auth-web/app/api/admin/topics-queue/route.ts`**의 `POST` 핸들러(`:456-699`, `requireSuperAdmin` 게이트):
1. 대상 카테고리(이름/키워드/벤치마크 채널/장르/기본 스타일) + 정산 정책 로드
2. 카테고리당 **10개 주제**를 요청하는 대형 프롬프트 구성(`:528-593`, 스타일 allow-list로 제약)
3. `generateJsonWithModelSetting(supabase, prompt, 'sys_api_topic_generation_model', geminiApiKey)`(`auth-web/lib/aiRouter.ts:61-86`) 호출 — **웹어드민 전역설정 `global_settings.sys_api_topic_generation_model`이 모델을 결정**, `claude`로 시작하면 Anthropic, 아니면 Gemini, Claude 실패 시 Gemini로 자동 폴백
4. `pickPreferredWorker()`로 작업자 배정, 정책에 맞춰 길이 clamp, `estimated_payout` 계산 후 `topics_queue`에 `status:'pending'`으로 bulk insert
5. 백그라운드로 `translateAndSaveTopics()` 실행(vi/en/th 사전번역, `sys_api_translation_model` 사용)

**결론: 주제 생성의 모델/프로바이더/프롬프트는 전부 웹어드민(Next.js 서버)이 통제하며, Python
데스크톱 앱은 관여하지 않는다.**

### 2d. 휴면 상태인 인앱 생성기
`services/dispatcher_service.py`(파일 헤더에 `[DEPRECATED][AIR-0150]` 명시 — "주제 생성과 작업자
배정은 이제 웹어드민이 소유한다. 롤백용으로만 보존") — `dispatch_daily_topics()`가 카테고리당
주제 1개를 하드코딩된 `gemini-2.5-flash`로 직접 생성한다. `ENABLE_USER_APP_DISPATCHER=true`일
때만 동작(`main.py:1781-1786`), 기본값 `false` — **현재 비활성.**

### 2e. `TOPIC_GENERATION_MODEL`은 죽은 값
`services/web_admin_client.py:60`이 `sys_api_topic_generation_model → TOPIC_GENERATION_MODEL`을
데스크톱 `config.py`에 동기화하지만, **Python 코드 어디에서도 `config.TOPIC_GENERATION_MODEL`을
읽지 않는다** — 대칭성을 위해 동기화만 될 뿐 실사용처가 없다.

## 3. 요청/응답 스키마

### `GET /api/user/recommended-topics`
쿼리: `filter_duration`, `filter_language`, `filter_category`, `limit=20`, `refresh=False`
응답: `{"status":"ok","topics":[Topic],"cached":bool}`, `Topic` = `{id, topic, category_name,
category_id, language, language_label, duration_minutes, recommended_duration_minutes,
script_style, image_style, estimated_payout, estimated_payout_usdt, payout_multiplier,
adjusted_payout, adjusted_payout_usdt, created_at, video_type}`

### `POST /api/user/claim-topic`
요청: `{topic_id: str}` → 응답: `{"status":"ok","project_id":int,"project_mode":str,
"topic":{id,topic,language,recommended_duration_minutes,estimated_payout,script_style,
image_style,category_name}}`

### `topics_queue` (Supabase, 재구성)
```
id, category_id, topic, topic_vi, topic_en, topic_th,
category_name_vi, category_name_en, category_name_th,
translated_at, translation_status, language, status, is_auto_generated,
assigned_employee_email, assigned_at, assigned_script_style, assigned_image_style,
recommended_duration_minutes, assigned_duration_minutes, duration_locked, duration_reason,
difficulty_level, estimated_payout, actual_payout, payout_policy(jsonb),
video_clip_ratio, total_scenes, video_scenes, image_scenes, asset_mix_summary(jsonb),
local_project_id, progress_payload(jsonb), progress_updated_at, created_at
```
`categories(*)` 조인이 사실상 필수 의존(name, keywords, benchmark_channel_url, target_country,
language, video_type, default_script_style, default_image_style).

`user_topic_recommendations`(사용자별 7일 캐시): `user_id, employee_email, topic_queue_id, topic,
language, recommended_duration_minutes, estimated_payout, script_style, image_style, category_id,
category_name, payout_multiplier, is_claimed, claimed_at, expires_at, created_at`

### Stage B 진입점 (`/api/gemini/generate-structure`, 대비용)
요청: `{project_id?, topic, duration=60, tone="informative", notes?, target_language="ko",
script_style="story", mode="monologue"}` → 응답: `{"status":"ok","structure":{...}}`

## 4. 저장/선택/Stage B 인계

`claim_topic()`이 SQLite에 쓰는 값 (`database.py`):
- `projects`: `name`(주제 80자 절단), `topic`, `language`, `employee_email`, `sync_id`
- `project_settings`(EAV, `update_project_setting()`): `app_mode`, `topic_queue_id`,
  `topic_queue_category_id`, `target_language`, `script_style`, `image_style`,
  **`style_locked="1"`**(Stage B에서 스타일 드롭다운 비활성화), `duration_seconds`,
  `assigned_duration_minutes`, **`duration_locked`**(길이 입력 비활성화), `estimated_payout`,
  `duration_reason`, `difficulty_level`, `payout_policy_json`

**Stage A → Stage B 인계 필드 세트**: `projects.topic`, `target_language`, `script_style`(+lock),
`image_style`, `app_mode`(`/script-plan` vs `/music-plan` 라우팅 결정), `duration_seconds`(+lock),
`topic_queue_id`/`topic_queue_category_id`(역참조).

**리버스 싱크**: `services/topic_queue_sync_service.sync_topic_progress()`가 로컬 파이프라인
진행률(`script_structure`/`script`/`image_prompts`/`tts` 존재 여부)을 계산해 같은 `topics_queue`
행에 `local_project_id`/`progress_payload`로 다시 PATCH — 웹어드민이 claim된 주제의 진행 상황을
볼 수 있게 함.

**발견한 버그성 이슈**: `/script-plan?...&auto=true`의 `auto=true`가 `script_plan.html`에서
**전혀 읽히지 않음** — 자동으로 대본 구조 생성을 트리거하려던 의도로 보이나 죽은 코드. 이번
작업 범위 밖이라 수정하지 않고 기록만 함.

## 5. 중복 방지 및 사용 이력 관리 — **존재하지 않음**

`auth-web/app/api/admin/topics-queue/route.ts`(주제 생성 지점) 전체를 `duplicate|similar|dedup|중복`
키워드로 검색한 결과 **0건.** 있는 건 `user_topic_recommendations`의 7일 만료 캐시(추천 신선도
관리)와 `topics_queue.status`(claim 여부 추적)뿐 — **콘텐츠 유사도/중복 검사 로직 자체가 없다.**
즉 Hermes PoC가 요구하는 "사용 이력과의 중복 검사"는 신규 기능이며, 이게 이번 과제의 핵심
가치 제안이 맞다는 것을 확인함.

## 6. STD/PRO 분기 및 웹어드민 AI 모델 설정 영향

- **STD**: claim-큐 UI만 노출(`projects.html`), "새 프로젝트" 버튼 숨김 → 오직 `topics_queue`에서
  claim하거나 관리자가 사전배정한 주제(`get-daily`)만 사용 가능.
- **PRO**(`is_independent`류 판정): `openProjectModal()` → `createNewProject()`(`templates/base.html`)로
  주제 문자열을 직접 입력해 큐를 완전히 우회하는 수동 생성 가능 — AI 관여 없음, 그냥 빈 프로젝트 생성.
- **웹어드민 AI 모델 설정 영향 범위**: `global_settings.sys_api_topic_generation_model`(claim
  큐를 채우는 생성 모델), `sys_api_translation_model`(사전번역) — 둘 다 `auth-web` 쪽에서만
  소비됨. Python 쪽 동일 이름 설정(`config.TOPIC_GENERATION_MODEL`)은 죽은 값(§2e).

## 7. "기존 ai_router 기반 주제 생성" 폴백에 대한 재정의 필요성

지시사항 원칙 #7 "Hermes 실패 시 기존 ai_router 기반 주제 생성으로 폴백해야 한다"는 **STD
흐름에 실제로 존재하지 않는 대상을 폴백으로 지정**하고 있다. 두 가지 해석이 가능하고,
설계 문서(§아키텍처)에서 후자를 채택함:

- (a) `services/ai_router.py::generate_text()`를 직접 사용해 **새로운 프롬프트 기반 폴백**을
  Python 쪽에 신규로 만든다 (기존 `dispatcher_service.py`의 정신을 계승하되 ai_router로 통일).
- (b) Hermes 실패 시 단순히 **기존 `topics_queue`의 pending 항목을 그대로 반환**한다(사용자
  입장에서는 "AI 강화가 빠진 평소 추천"으로 자연스럽게 저하).

(a)는 "완전한 신규 개발"이라 이번 PoC 범위를 넘어서고, (b)는 기존 계약을 전혀 깨지 않으면서
"폴백"의 실질적 의미(사용자가 빈손으로 남지 않음)를 만족시킨다. **설계 문서는 (b)를 기본으로
하되, Python `ai_router.generate_text()`를 사용하는 (a)를 "AIR Topic Service" 내부의 2차
폴백(정말 아무 pending 항목도 없을 때)으로 포함**하는 절충안을 제안한다.

## Files Changed
없음 (조사·문서만). 이 보고서 1개 파일 신규.
