# AIR Topic Intelligence (Hermes 기반) — 아키텍처 설계

- 상태: **설계안 / CTO 승인 대기** (코드 연결 없음)
- 선행 문서: [`worknote/AIR-0226-stage1-current-state-analysis.md`](../worknote/AIR-0226-stage1-current-state-analysis.md)
- 관련 문서: [DATA_MODEL](./HERMES_TOPIC_INTELLIGENCE_DATA_MODEL.md), [POC](./HERMES_TOPIC_INTELLIGENCE_POC.md), [SECURITY](./HERMES_TOPIC_INTELLIGENCE_SECURITY.md)

## 0. 이 설계가 반드시 반영해야 하는 현행 사실 (Stage 1에서 확인됨)

1. STD 사용자의 "AI 추천 주제"는 **실시간 개인화 생성이 아니라, 관리자가 채워둔 공용 큐
   (`topics_queue`)에서 스코어링된 슬라이스**다. 사용자 요청 경로에 LLM 호출이 없다.
2. `topics_queue`를 채우는 AI 호출은 **`auth-web`(Next.js)**에서만 일어난다
   (`app/api/admin/topics-queue/route.ts`). 데스크톱 Python 앱은 이 생성에 관여하지 않는다.
3. **중복/유사도 검사가 현재 전혀 없다** — 이게 이번 기능의 진짜 존재 이유다.
4. 지시사항이 전제한 "기존 ai_router 기반 폴백"은 STD 흐름에 실재하지 않아, 이 설계에서
   새로 정의한다(§6).

이 사실들 때문에 Hermes를 "사용자가 버튼을 누르는 순간 실시간으로 대신 호출되는 대체 모델"로
설계하면 안 된다 — 그건 존재하지도 않는 실시간 생성 경로를 만드는 것이 되어 원칙 #1("STD 주제
생성 흐름을 우선 대상으로")과 #2("기존 계약을 깨지 않는다")를 동시에 어기게 된다. 대신 **Hermes는
`topics_queue`를 채우는 파이프라인을 보강하는 "지능 레이어"**로 설계한다.

## 1. 전체 구조

```
                         ┌─────────────────────────────────────────┐
                         │         Nous Research Hermes Agent        │
                         │   (외부 서버 또는 로컬 PoC 프로세스,        │
                         │    데스크톱에 내장하지 않음)                │
                         └───────────────┬─────────────────────────┘
                                          │ HTTPS, 제한된 내부 API만 호출
                                          │ (Supabase 자격증명 절대 미제공)
                         ┌───────────────▼─────────────────────────┐
                         │           AIR Topic Service                │
                         │  (데스크톱 앱에 내장된 FastAPI 라우터/서비스 │
                         │   app/routers/topic_intelligence.py +      │
                         │   services/topic_intelligence_service.py)  │
                         │                                             │
                         │  - Hermes가 부를 수 있는 유일한 진입점       │
                         │  - 시장조사 컨텍스트 조회 API (읽기전용)     │
                         │  - 후보 제출 API (쓰기, 검증 후 저장)        │
                         │  - tenant_id/channel_id 스코프 강제         │
                         │  - 모든 호출 감사 로그 기록                  │
                         └───────┬─────────────────────┬─────────────┘
                                 │                       │
                     동기(사용자 요청, 캐시 우선)   비동기(정기 시장조사 잡)
                                 │                       │
                    ┌────────────▼──────────┐  ┌─────────▼──────────────┐
                    │  기존 claim-큐 흐름     │  │  topic_research_jobs    │
                    │  (변경 없음)            │  │  topic_candidates       │
                    │  GET recommended-topics │  │  (신규 Supabase 테이블) │
                    │  POST claim-topic       │  └─────────┬──────────────┘
                    └────────────┬────────────┘             │
                                 │                    승격(threshold/관리자 승인)
                                 └──────────◄───── topics_queue INSERT ──┘
                                    (기존 관리자 생성기와 동일한 shape)
```

**핵심 설계 결정**: Hermes의 산출물은 `topics_queue`에 **직접** 꽂히지 않는다. 반드시
`topic_candidates`(신규 테이블, Stage 3)를 거친다. 이 중간 단계가 있어야:
- 기존 `claim_topic()`/`get_recommended_topics()`가 **전혀 수정 없이** 계속 동작한다
  (원칙 #2 준수 — 두 함수는 `topics_queue`만 알고 `topic_candidates`의 존재 자체를 모른다).
- 점수 임계값 미달 후보나 위험 플래그(`risk_flags`)가 붙은 후보를 큐에 자동 승격하지 않고
  관리자 검토로 보낼 수 있다.
- Hermes가 실패/저품질이어도 `topics_queue`가 오염되지 않는다.

## 2. 동기식 생성 vs 정기 시장조사 작업 분리

### 2a. 동기식 경로 (사용자가 화면에서 "AI 추천 새로고침"을 누르는 순간)
- **Hermes를 직접 호출하지 않는다.** Hermes 에이전틱 조사(시장 조사 + 20개 생성 + 랭킹)는
  수십 초~수 분이 걸릴 수 있어 동기 요청에 부적합하다.
- 대신: (1) 이미 승격되어 `topics_queue`에 있는 항목을 기존 로직 그대로 반환 → (2) 캐시된
  `topic_candidates`(아직 미승격이지만 점수가 준수한) 중 이 사용자/채널에 맞는 것을 얹어서
  보여줄 수도 있음(선택 사항, PRO 확장 시 고려) → (3) 정말 아무 것도 없으면 §6의 폴백.
- 즉 사용자 체감 응답 속도는 **오늘과 동일**하게 유지된다.

### 2b. 정기 시장조사 작업 (비동기, Hermes가 실제로 도는 곳)
- 트리거: (a) 관리자가 웹어드민에서 카테고리/채널 단위로 수동 실행(기존 `topics-queue`
  생성 버튼과 나란히 "Hermes 강화 생성" 버튼 추가하는 형태를 제안), 또는 (b) 정기 배치
  (일 1회, 카테고리/채널별) — 실행 위치는 **PoC 단계에서는 로컬/별도 서버**, 운영 전환 시
  스케줄러 방식은 AIR-0225B에서 이미 검토한 것과 같은 선택지(Vercel Cron 등)를 재사용 검토.
- `AIR Topic Service`가 잡을 생성(`topic_research_jobs` INSERT, `status='queued'`) → Hermes에
  전달할 컨텍스트(카테고리, 채널 기억, 최근 사용 이력 요약)를 조립 → Hermes를 HTTPS로 호출 →
  응답을 검증(JSON Schema, §4) → `topic_candidates`에 저장 → 점수/위험도 기준으로 자동승격
  또는 관리자 검토 큐에 표시.

## 3. Hermes 조사 결과의 캐시·재사용

- `topic_research_jobs` 1건 = "이 카테고리/채널에 대해 이 시점에 수행한 조사 1회".
- `topic_candidates`는 `topic_research_jobs`에 FK로 연결 — **한 번의 조사에서 나온 후보들은
  재사용 가능** (예: 오늘 사용자가 claim하지 않은 후보는 내일도 유효할 수 있음, 유효기간은
  `topic_candidates.expires_at`로 관리, `user_topic_recommendations`의 7일 캐시 관례를 참고해
  기본 7일 제안).
- 동일 카테고리/채널에 대해 유효기간 내 최근 조사가 이미 있으면, 정기 작업은 **새로 Hermes를
  부르지 않고 스킵**(비용 절감) — 단, 관리자가 "강제 새로고침"을 요청하면 예외.

## 4. Hermes 출력 JSON 스키마

PoC 문서(§POC)와 데이터 모델(§DATA_MODEL `topic_candidates`)에 동일하게 반영되는 단일 스키마:

```json
{
  "candidates": [
    {
      "title": "string",
      "core_concept": "string",
      "summary": "string",
      "category": "string",
      "target_country": "string (ISO 3166-1 alpha-2)",
      "target_language": "string (ko|en|ja|vi|th)",
      "target_age": "string, 예: '50-70'",
      "emotions": ["string", "..."],
      "trend_reason": "string",
      "score_channel_fit": "number 0-100",
      "score_novelty": "number 0-100",
      "score_trend": "number 0-100",
      "score_competition": "number 0-100",
      "score_retention": "number 0-100",
      "score_total": "number 0-100",
      "similar_topic_ids": ["string", "..."],
      "evidence": ["string", "..."],
      "risk_flags": ["string", "..."]
    }
  ],
  "research_context_summary": "string",
  "model_version": "string",
  "generated_at": "ISO8601"
}
```

- `similar_topic_ids`는 Hermes가 스스로 판단한 값이 아니라, `AIR Topic Service`가 제공한
  사용 이력(§3, 아래 "제한된 내부 API")과 대조해 Hermes가 채워 넣는 필드 — Hermes에게 원문
  DB 접근권이 없으므로, 대조할 이력 자체를 **AIR Topic Service가 요청 컨텍스트에 미리 넣어준다**
  (예: 최근 200개 제목/핵심사건 요약 리스트). Hermes는 그 리스트 안의 id만 참조 가능.
- 스키마 미준수(필수 필드 누락, 타입 불일치, score 범위 이탈)는 **파싱 단계에서 즉시 실패
  처리**하고 해당 조사 잡을 `status='invalid_output'`으로 기록, §6 폴백 트리거.

## 5. Hermes가 호출 가능한 제한된 내부 API (AIR Topic Service가 제공)

Hermes는 Supabase에 직접 연결하지 않는다(원칙 #4, #5, #6). `AIR Topic Service`가 아래 2개
엔드포인트만 노출한다(둘 다 tenant_id/channel_id로 스코프 강제, §SECURITY §3):

| 엔드포인트 | 방향 | 내용 |
|---|---|---|
| `GET /internal/topic-intel/research-context?category_id=&channel_id=` | Hermes ← AIR Topic Service | 카테고리 메타(이름/키워드/벤치마크), `channel_content_profile` 요약, 최근 사용 이력 제목/핵심사건 리스트(최대 N개, PII 없음) |
| `POST /internal/topic-intel/submit-candidates` | Hermes → AIR Topic Service | §4 스키마의 후보 배열 제출. 서버가 스키마 검증 + 위험도 재계산 후 `topic_candidates`에 저장 |

이 두 엔드포인트 외에 Hermes가 도달 가능한 다른 내부 API는 없음 — 회원/결제/추천인/출금/관리자
설정 관련 라우터는 전혀 노출하지 않는다(원칙 #6, 구체적 위험/대응은 §SECURITY).

## 6. 기존 `ai_router` 폴백 (신규 정의, Stage 1 §7 참고)

Hermes 조사가 실패(타임아웃/스키마 불일치/서버 오류)하거나 결과가 없을 때:

1. **1차 폴백**: `topics_queue`의 기존 `pending` 항목(관리자 생성기가 채운 것)을 평소대로
   반환 — 사용자 입장에서는 "AI 강화가 빠진 평소 추천"으로 자연스럽게 저하, 빈손이 되지 않음.
2. **2차 폴백**(1차도 소진된 극단적 경우): `AIR Topic Service`가 `services/ai_router.py::generate_text()`를
   직접 호출해 카테고리 프롬프트 기반으로 후보를 생성 — `dispatcher_service.py`(현재 비활성)의
   프롬프트 정신을 계승하되 `ai_router`로 통일, 생성 결과는 그대로 `topics_queue`에 넣지 않고
   반드시 `topic_candidates`를 거쳐 같은 검증 경로를 타게 한다(일관성 유지).
3. 두 폴백 모두 `topic_research_jobs.status`와 감사 로그에 "hermes_failed_fallback_used" 형태로
   기록해, 실패율 지표(§평가 기준)에 반영되게 한다.

## 7. tenant_id / channel_id 격리

- 현행 스키마에는 이미 `tenant_key`/커미션율 등 멀티테넌트 개념이 부분적으로 존재
  (`services/web_admin_client.py`의 `get_all_tenants`/`update_tenant_commission` 등, AIR-0225B
  조사에서 확인). 이번 신규 테이블은 전부 `tenant_id`를 명시적으로 포함해 이 개념과 정렬한다.
- `channel_id`는 이번 기능에서 **신규 도입하는 개념**이다 — "채널 기억"(목표 문구 원문)을
  구현하려면 "어느 유튜브 채널에 대한 조사/기록인가"를 명시적으로 구분해야 한다. 기존
  프로필의 `youtube_channel`/`youtube_handle` 필드를 `channel_content_profile`의 자연키로
  삼거나, 신규 `channels` 참조 테이블을 별도로 둘지는 CTO 결정 필요 항목으로 남긴다
  (Stage 3에서는 우선 `channel_id TEXT`로 느슨하게 정의).
- 모든 조회/저장 API는 호출 시점의 tenant_id/channel_id로 필터링되며, Hermes에게 전달되는
  컨텍스트도 해당 tenant/channel 범위를 벗어난 데이터를 포함하지 않는다.

## 8. 실행시간·호출비용·외부 접근 범위 제한

- **실행시간**: `AIR Topic Service`가 Hermes 호출에 하드 타임아웃 설정(PoC 단계 제안값 120초,
  운영 전환 시 실측 후 조정). 초과 시 즉시 §6 폴백.
- **호출비용**: `topic_research_jobs`에 `estimated_cost_usd`/`actual_cost_usd`(있으면) 필드로
  기록(Stage 3). 카테고리/채널당 일일 최대 조사 횟수 상한을 서버 설정으로 둔다(초기값 제안:
  카테고리당 1회/일 — §3 캐시 재사용과 결합하면 자연스럽게 이 상한을 지키게 됨).
- **외부 접근 범위 제한**: Hermes가 나가는 아웃바운드 네트워크는 (a) 자기 자신의 LLM
  추론 백엔드, (b) `AIR Topic Service`의 2개 내부 API 엔드포인트로만 제한하는 것을 운영 배포
  시 요구사항으로 명시(PoC 단계에서는 로컬 프로세스라 강제하기 어려우므로 §POC 문서에서
  "PoC 한정 예외"로 명시).

## 9. 감사 로그

모든 에이전트 실행(조사 잡 시작/완료/실패, Hermes 호출, 내부 API 호출, 폴백 발동, 후보 승격/반려)을
`topic_research_jobs`(잡 단위)와 별도 감사 로그(Stage 3 §감사) 형태로 기록 — 상세 스키마는
[DATA_MODEL 문서](./HERMES_TOPIC_INTELLIGENCE_DATA_MODEL.md) 참고. AIR-0225B에서 확립한
"RLS enabled + 정책 없음(service_role/내부 API 전용)" 컨벤션을 그대로 따른다.

## 10. STD 적용 범위 / PRO 확장 범위 (요약, 상세는 완료보고서에서 재정리)

- **STD (이번 우선 대상)**: `topics_queue` 승격 경로만 사용, 사용자는 오늘과 동일한 claim UI를
  그대로 씀 — 눈에 보이는 변화는 "추천 품질이 좋아짐"과 "중복이 줄어듦" 뿐.
- **PRO (향후 확장, 이번 범위 아님)**: `channel_content_profile` 개인화, 미승격
  `topic_candidates`를 PRO 전용 화면에서 직접 열람/선택하는 실시간에 가까운 경험, 채널별
  성과 피드백 루프(`topic_performance`) 반영 강화.
