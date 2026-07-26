# AIR Content Intelligence (Hermes 기반) — 기획/대본생성 확장 설계

- 상태: **설계안 / 검토용** (코드 연결 없음)
- 선행 문서: [`HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE.md`](./HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE.md)(Stage A, 이미 CTO 승인 대기 상태로 작성됨), [`HERMES_TOPIC_INTELLIGENCE_DATA_MODEL.md`](./HERMES_TOPIC_INTELLIGENCE_DATA_MODEL.md), [`HERMES_TOPIC_INTELLIGENCE_SECURITY.md`](./HERMES_TOPIC_INTELLIGENCE_SECURITY.md)
- 이 문서는 위 3개 문서가 이미 다룬 **Stage A(주제 생성)는 그대로 재사용**하고, **Stage B(대본 기획)/Stage C(대본 생성)** 두 단계로 Hermes 확장을 이어붙이는 것만 새로 설계한다. 보안 원칙(#1~#6, 자격증명 미제공, tenant/channel 스코프 강제, 동기 경로 불변, 스키마 검증, 전부-아니면-전무 저장, "AI 점수 = 성과 보장 아님" 문구 금지)은 그대로 승계한다 — 이 문서에서 재정의하지 않는다.

---

## 0. 이 확장이 필요한 이유 — 조사로 확인된 사실

Hermes를 기획/대본생성까지 확장하기 전에, **지금 이 두 단계가 실제로 어떻게 동작하는지**부터 코드 레벨로 확인했다. 결과가 예상과 달랐다.

### 0-1. 기획(Planning) 단계 — "중복 방지"가 이미 있었는데 죽어있다

`app/routers/gemini.py`의 `generate_script_structure_api`(`POST /api/gemini/generate-structure`)는 함수 docstring에 **"대본 구조 생성 (중복 방지 적용)"**이라고 써있다. 실제 코드를 보면:

```python
recent_projects = db.get_recent_projects(limit=5)
recent_titles = [p['name'] for p in recent_projects]          # 계산만 하고 어디에도 안 씀
...
accumulated_knowledge = db.get_recent_knowledge(limit=10, script_style=req.script_style)  # 계산만 하고 어디에도 안 씀
...
result = await scene_planner_service.plan_scenes(
    topic=req.topic, target_duration=req.duration,
    project_id=req.project_id, style_directive=style_directive
)  # recent_titles도 accumulated_knowledge도 전달 안 됨 — plan_scenes()는 애초에 받을 파라미터도 없음
```

**대조**: AIR-0209(2026-07-07, PR #65) 리팩토링 이전 버전인 `services/gemini_service.py:805`의 (지금은 죽은) `generate_script_structure()`는 실제로 이 두 값을 프롬프트에 넣고 있었다 — `recent_titles` → "이 주제들은 반복하지 마라", `accumulated_knowledge`(`success_knowledge` 테이블) → "누적된 성공 전략" 섹션. AIR-0209가 **씬 구조 일관성(Scene Source of Truth)은 확보했지만, 그 과정에서 이 다양성 메커니즘을 회귀시켰다.**

### 0-2. 대본 생성(Script Generation) 단계 — 애초에 그런 로직이 있었던 적이 없다

`/api/script/generate`는 씬(섹션) 개수만큼 클라이언트(JS)가 루프를 돌며 순차 호출한다(`script_gen.html`). 중복/유사도 검사, 채널 톤 일관성, "최근에 이런 표현 썼음" 같은 어떤 형태의 교차-프로젝트 기억도 처음부터 없었다.

### 0-3. 결론

**사용자가 우려하는 "여러 워커가 같은 카테고리로 계속 뽑을 때 겹치는 문제"는 Hermes가 없어서가 아니라, 원래 있던 소박한 방지 로직이 리팩토링 중 실수로 빠졌기 때문이기도 하다.** 따라서 이 문서는 두 갈래로 제안한다:

- **Phase 0(즉시, Hermes 무관)**: §5에서 별도로 제안 — `scene_planner.py`에 최근 이력을 다시 배선하는 반나절짜리 수정. Hermes 없이도 지금 당장 체감 개선이 가능하다.
- **Phase 2~3(이 문서의 본 설계, Hermes 기반)**: Phase 0을 훨씬 정교하게 확장한 버전 — "최근 제목 5개 피하기"가 아니라 "이 채널이 최근에 쓴 훅 패턴/템포/화자 스타일을 실제로 학습해서 반영"하는 수준.

---

## 1. 설계 원칙 승계 + 이번 확장에서 추가되는 제약

기존 문서의 원칙 #1~#6에 더해, 이번 확장은 다음을 추가로 지킨다:

- **AIR-0209 Scene Source of Truth를 절대 어기지 않는다.** 기획 단계에서 확정된 `scenes[]`는 여전히 유일한 진실이며, 하위 단계(대본생성 이후)에서 씬을 다시 나누거나 재구성하는 코드는 이번 확장 어디에도 만들지 않는다. Hermes의 개입은 "씬 구조를 다시 만드는 것"이 아니라 "씬 구조를 만들 때/대본을 쓸 때 참고할 맥락을 풍부하게 해주는 것"으로 한정한다.
- **동기 경로(사용자가 "구조 생성"/"대본 생성" 버튼을 누르는 순간)는 오늘과 정확히 같은 모양을 유지한다.** 기획 1콜, 대본생성 N콜(씬당 순차)이라는 현재 호출 구조·횟수·순서를 이번 확장이 늘리거나 바꾸지 않는다 — Hermes가 만드는 건 이 호출들의 **프롬프트에 주입되는 컨텍스트**이거나, 완전히 **별도 옵션 UI**다.

---

## 2. 전체 구조 (Stage A/B/C 통합)

```
                    ┌─────────────────────────────────────────────┐
                    │         Nous Research Hermes Agent             │
                    └───────────────────┬─────────────────────────┘
                                         │ HTTPS, 제한된 내부 API만
                    ┌────────────────────▼─────────────────────────┐
                    │              AIR Content Service                 │
                    │  (기존 "AIR Topic Service"를 3단계로 확장 —       │
                    │   app/routers/content_intelligence.py 등)         │
                    └───┬──────────────────┬──────────────────┬──────┘
                        │                  │                  │
                 Stage A: 주제       Stage B: 기획       Stage C: 대본생성
                 (기존 문서 그대로)   (신규, §3)          (신규, §4)
                        │                  │                  │
              topics_queue         scene_planner.py    /api/script/generate
              (승격, 변경없음)      (프롬프트 보강만)     (프롬프트 보강만)
```

핵심은 Stage B/C가 Stage A와 **모양이 다르다**는 점이다. Stage A는 "Hermes가 후보를 만들고 사람이 승격/claim"하는 구조였지만, Stage B/C는 씬 순서·개수를 건드릴 수 없으므로 대부분 **"Hermes가 배경에서 채널 기억을 갱신 → 동기 호출의 프롬프트가 그 기억을 읽어서 참고"** 하는, 훨씬 조용한 형태다.

---

## 3. Stage B — Planning Intelligence

### 3-1. 산출물 층위 (2개, 독립적으로 켜고 끌 수 있음)

**(1) 채널 서사 기억 갱신 — 필수 권장, 저위험**

- Hermes가 비동기로(정기 배치 또는 프로젝트 완료 트리거) 이 채널/카테고리의 최근 완료 프로젝트들의 `scenes[]`를 분석해, "최근에 쓴 훅 유형", "자주 쓰는 템포/장소 패턴", "반복된 감정 곡선"을 요약해 `channel_narrative_memory`(§5)에 저장.
- `scene_planner.plan_scenes()`가 호출될 때(동기 경로, 변경 없음), 프롬프트에 이 요약을 "최근에 이런 구조를 썼으니 다르게 가라" 형태로 주입 — **AIR-0209 이전 `recent_titles`/`accumulated_knowledge` 메커니즘의 고도화 버전**이지 완전히 새로운 개념이 아니다.
- 사용자 체감: 버튼 동작·응답속도·화면 전부 오늘과 동일. 결과물의 다양성만 올라간다.

**(2) 대안 기획 후보 — 선택적, Stage A와 같은 모양**

- Hermes가 미리 완전히 다른 씬 구조 초안을 만들어 `scene_plan_candidates`(§5)에 저장해두고, 기획 화면에 "Hermes 추천 구조 불러오기" 버튼을 하나 더 둔다(기본 "구조 생성" 버튼은 그대로 존재).
- 사용자가 이 버튼을 눌러야만 로드됨 — 자동 적용 없음. Stage A의 topic_candidates와 동일한 "승격/선택은 사람이" 철학.
- 이건 Phase 3(§6)로 미루는 걸 권장 — (1)보다 구현 범위가 크고, 지금 확인된 문제(§0)를 고치는 데 필수는 아니다.

---

## 4. Stage C — Script Generation Intelligence

### 4-1. 씬 재분할 금지 재확인

Hermes가 "완성된 대본 후보"를 통째로 만들어서 기존 `scenes[]` 구조를 무시하고 밀어넣는 설계는 **이번 확장에서 하지 않는다.** 이는 AIR-0209가 명시적으로 금지한 "하위 단계에서 대본 전문을 다시 LLM에 넘겨 씬을 재분할"과 본질적으로 같은 패턴이기 때문이다.

### 4-2. 산출물

**(1) 채널 서사 기억 → 씬별 생성 프롬프트 보강 — 필수 권장**

- §3-1(1)에서 Hermes가 갱신하는 `channel_narrative_memory`에 "최근에 쓴 대사 패턴/화자 이름/클리셰 표현"을 추가로 축적.
- `/api/script/generate`가 씬마다 호출될 때(동기 경로, 횟수·순서 변경 없음) 이 요약을 프롬프트에 "이런 이름/표현은 피하라"로 주입 — 지금 이미 있는 `introducedCharacters`(같은 프로젝트 내 씬 간 캐릭터 연속성) 로직과 **같은 층위**에, "이번 프로젝트뿐 아니라 이 채널 전체의 최근 이력"이라는 범위만 넓힌 것.

**(2) 비동기 내러티브 QA — 선택적**

- 대본이 완성된 뒤, Hermes가 `channel_narrative_memory`와 대조해 "이 씬은 지난 프로젝트와 유사도가 높다"류의 `risk_flags`/유사도 점수를 매겨 `script_qa_events`(§5)에 기록.
- 자동으로 아무것도 고치지 않는다 — 관리자/작성자 화면에 배지로만 노출, 사람이 볼지 말지·수정할지 결정. Stage A 문서의 "AI 점수는 성과 보장이 아니다" 원칙과 같은 이유로, 이 QA 점수도 "참고용 유사도 경고"로만 표현한다.

---

## 5. 데이터 모델 확장 (기존 DATA_MODEL 문서 컨벤션 그대로: UUID PK, tenant_id/channel_id, RLS enabled + service_role 전용, JSONB, created_at/updated_at 트리거)

```sql
-- 기존 channel_content_profile(Stage A 문서)을 서사 기억까지 담도록 확장
-- (신규 컬럼만 추가 — additive, 기존 컬럼 변경 없음)
ALTER TABLE public.channel_content_profile
    ADD COLUMN IF NOT EXISTS recent_hook_patterns   JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS recent_pacing_notes     JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS recent_character_names  JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS recent_phrase_patterns  JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Stage B-(2) 전용, Phase 3에서만 필요
CREATE TABLE IF NOT EXISTS public.scene_plan_candidates (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          TEXT NOT NULL,
    channel_id         TEXT,
    topic_candidate_id UUID REFERENCES public.topic_candidates(id),  -- Stage A와 연결 가능(옵션)
    project_id         BIGINT,                     -- 데스크톱 SQLite projects.id, 느슨한 참조
    scenes             JSONB NOT NULL,              -- scene_planner.py와 동일한 scenes[] 스키마 그대로
    score_novelty      NUMERIC(5,2),
    score_channel_fit  NUMERIC(5,2),
    status             TEXT NOT NULL DEFAULT 'candidate'
                           CHECK (status IN ('candidate','loaded','rejected','expired')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.scene_plan_candidates ENABLE ROW LEVEL SECURITY;

-- Stage C-(2) 전용, Phase 3에서만 필요
CREATE TABLE IF NOT EXISTS public.script_qa_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    channel_id      TEXT,
    project_id      BIGINT,
    scene_id        TEXT,
    similarity_score NUMERIC(5,2),
    risk_flags      JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_against JSONB NOT NULL DEFAULT '[]'::jsonb,  -- 어떤 과거 프로젝트/씬과 비교했는지(감사용)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.script_qa_events ENABLE ROW LEVEL SECURITY;
```

Hermes 노출 API도 기존 2개(`research-context`/`submit-candidates`)와 같은 모양으로 2개 더 추가(내부 API, Hermes는 여전히 Supabase 자격증명 미보유):

| 엔드포인트 | 방향 | 내용 |
|---|---|---|
| `GET /internal/content-intel/narrative-context?channel_id=` | Hermes ← AIR Content Service | `channel_narrative_memory` 요약(화이트리스트, PII 없음) |
| `POST /internal/content-intel/submit-narrative-update` | Hermes → AIR Content Service | 완료된 프로젝트 분석 결과로 `channel_content_profile`의 신규 컬럼들 갱신 제안 |

---

## 6. 실행 순서 제안 (Phase)

| Phase | 내용 | 전제 |
|---|---|---|
| **Phase 0** | `scene_planner.py`에 `recent_titles`/`accumulated_knowledge` 재배선 (반나절) | Hermes 불필요, 지금 바로 가능 |
| **Phase 1** | Stage A(주제) — 기존 `HERMES_TOPIC_INTELLIGENCE_*` 문서 그대로 PoC | CTO 승인 |
| **Phase 2** | Stage B-(1) + Stage C-(1) — `channel_narrative_memory` 파이프라인, 씬 기획/대본생성 프롬프트 보강만 | Phase 1의 Hermes 실행 인프라 재사용 |
| **Phase 3** | Stage B-(2) 대안 기획 후보 UI, Stage C-(2) 내러티브 QA 배지 | Phase 2 안정화 후, 선택적 |

Phase 0은 이번 확장 설계와 별개로 지금 바로 처리할 수 있는 작업이라 별도로 진행 여부를 여쭤보는 게 맞다고 판단해 이 문서에는 설계만 남기고 구현하지 않았다.

---

## 7. 리스크 / 미결정 사항 (기존 문서 승계 + 신규)

- `tenant_id`/`channel_id` 스코프 정의는 Stage A 문서와 동일하게 여전히 CTO 결정 필요 — 이번 확장도 그 위에 얹히므로 Stage A가 먼저 정리돼야 Stage B/C 스코프도 확정된다.
- 대본생성의 "씬당 순차 N회 호출"을 Hermes 도입과 무관하게 병렬화할지는 이번 설계 범위 밖 — 캐릭터 연속성(`introducedCharacters`) 로직이 순서 의존적이라, 단순 병렬화는 멀티보이스 모드에서 등장인물 폭증 문제를 다시 불러올 수 있다(§0-1에서 이미 한 번 고쳤던 문제).
- `success_knowledge` 테이블은 살아있지만 아무도 채우지 않는 상태로 보인다 — Phase 0/2 작업 시 이 테이블을 계속 쓸지, `channel_narrative_memory`로 대체 흡수할지 결정 필요.
