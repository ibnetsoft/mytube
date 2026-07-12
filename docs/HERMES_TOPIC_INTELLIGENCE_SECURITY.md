# AIR Topic Intelligence (Hermes) — 보안 설계

- 상태: **설계안 / CTO 승인 대기**
- 관련 문서: [ARCHITECTURE](./HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE.md), [DATA_MODEL](./HERMES_TOPIC_INTELLIGENCE_DATA_MODEL.md), [POC](./HERMES_TOPIC_INTELLIGENCE_POC.md)

이 문서는 AIR-0225B(service_role 유출 사고) 직후에 작성된다. 그 사고의 근본 원인 — "신뢰할 수
없는 실행 환경에 RLS 우회 자격증명을 쥐어준 것" — 을 이번 설계에서 반복하지 않는 것이 최우선
목표다.

## 1. 핵심 위협 모델: Hermes는 신뢰할 수 없는 실행 환경으로 취급한다

Hermes는 (a) 외부 서버 또는 (b) 로컬 PoC 프로세스에서 돈다 — 어느 쪽이든 **AIR Studio의
운영 Supabase 프로젝트를 직접 통제하는 인프라가 아니다.** AIR-0225B에서 확인했듯, "실행
위치가 우리 통제 밖"이라는 조건 하나만으로 그 실행 환경에 RLS 우회 키를 준다는 것 자체가
설계 결함이 된다. 따라서:

- Hermes는 **Supabase URL도, anon key도, service_role key도 받지 않는다.** Hermes가 아는 건
  자신을 호출한 `AIR Topic Service`의 내부 API 주소(§ARCHITECTURE §5)뿐이다.
- Hermes가 스스로 인터넷 어딘가에 있는 Supabase 프로젝트에 직접 접속할 방법이 원천적으로
  없다 — 이건 "약속"이 아니라 "자격증명을 아예 안 줌"으로 강제한다.

## 2. 데이터 접근 범위 제한 (원칙 #6 구체화)

Hermes에게 노출되는 것은 `GET /internal/topic-intel/research-context` 응답 **하나뿐**이며,
그 응답에 포함되는 필드는 명시적 화이트리스트로 제한한다:

| 포함 | 제외 (명시적으로 절대 포함 안 함) |
|---|---|
| 카테고리 이름/키워드/벤치마크 채널 URL | 회원 이메일/이름/연락처/국적 |
| `channel_content_profile` 요약(톤/반복 주제) | 결제/토큰 잔액/정산 정보 |
| 최근 사용 이력의 **제목 + 핵심사건 요약만** (`topic_usage_history.title`/`core_concept_summary`) | 추천인 트리/커미션/출금 데이터 |
| 조사 대상 tenant_id/channel_id (스코프 식별용) | 관리자 설정(API 키, 모델 설정 등 `global_settings` 원문) |
| | 다른 tenant/channel의 어떤 데이터도 |

`AIR Topic Service`가 이 화이트리스트를 강제하는 서버 코드(응답 조립 함수 하나)를 소유하며,
Hermes 쪽 프롬프트나 설정에는 이 범위를 넘는 필드를 요청할 방법이 없다(요청 파라미터가
`category_id`/`channel_id`뿐이므로 다른 데이터를 콕 집어 요청하는 것 자체가 불가능).

## 3. tenant_id / channel_id 스코프 강제

- `research-context` 응답과 `submit-candidates` 요청 모두 호출 시점에 **`AIR Topic Service`가
  스스로 해석한 tenant_id/channel_id**로 필터링한다 — Hermes가 요청 바디에 넣어 보낸
  tenant_id/channel_id를 그대로 신뢰하지 않는다(신뢰 경계는 항상 서버 쪽에서 결정).
- 즉 잡(`topic_research_jobs`)을 생성한 시점에 이미 tenant_id/channel_id가 서버에 의해
  고정되고, Hermes는 그 잡 컨텍스트 안에서만 동작 — 잡 하나가 여러 tenant/channel을 넘나들
  방법이 없다.

## 4. Hermes 실패/오작동에 대한 방어

- **스키마 미준수**: §ARCHITECTURE §4의 JSON Schema를 `submit-candidates`에서 서버가 검증.
  실패 시 `topic_research_jobs.status='invalid_output'`, 후보는 저장하지 않음(부분 저장 금지 —
  전부 아니면 전무, 오염 방지).
- **타임아웃**: 하드 타임아웃(제안 120초) 초과 시 연결 종료 + `status='timeout'` + 폴백 발동.
- **비정상적으로 많은/이상한 요청**: `submit-candidates`는 1회 잡당 후보 개수 상한(PoC 기준
  20개, §POC)을 서버가 강제 — 초과분은 자름, 실패시키지 않음(가용성 우선, 단 감사 로그에 기록).
- **악의적/오염된 출력 콘텐츠**: 후보 필드에 스크립트/HTML/SQL 인젝션 패턴이 있어도, 이 값들은
  전부 **파라미터화된 쓰기로만 DB에 들어가고, 사용자에게 보여질 때도 이스케이프**되므로(기존
  Jinja2/React 렌더링 관례 그대로 적용) 저장 자체는 안전 — 다만 "위험 플래그 자동 감지"를
  `submit-candidates` 검증 단계에 추가하는 것을 제안(예: 특정 금칙어/패턴 발견 시
  `risk_flags`에 서버가 강제로 추가).

## 5. 실행 환경/네트워크 격리 (PoC 단계 vs 운영 전환)

- **PoC 단계**: Hermes를 로컬 프로세스 또는 별도 격리 서버에서 실행. 이 단계에서는 네트워크
  아웃바운드를 강제로 제한하기 어려우므로, **대신 자격증명 자체를 아예 주지 않는 것으로
  방어**(§1) — "나갈 수 있는 곳이 제한되는가"가 아니라 "나가봐야 아무것도 못 하는가"로 위협을
  없앤다.
- **운영 전환 시(이번 범위 아님, 다음 Task 제안에 포함)**: Hermes 실행 환경의 아웃바운드
  방화벽 규칙으로 (a) 자기 LLM 추론 백엔드, (b) `AIR Topic Service`의 내부 API 도메인만 허용하는
  것을 요구사항으로 명시.

## 6. 사용자 신뢰/표현 관련 금지사항 (지시사항 6단계 반영)

- UI/문구에 **"실제 조회수 보장" 또는 Hermes 점수를 "조회수 예측"으로 표현하지 않는다.**
  `score_trend`/`score_total` 등은 명시적으로 "추천 참고 점수"로만 노출 — AIR-0225B의
  ChatGPT Plus 인증 뱃지 작업 때와 동일한 원칙("AI 결과만으로 확정하지 않는다"를 이번엔
  "AI 점수가 곧 성과 보장이 아니다"로 적용).
- 자동 유튜브 업로드, 사용자 승인 없는 자동 대본 생성은 이번 설계 어디에도 포함하지 않았다 —
  `topic_candidates`가 `topics_queue`로 승격되어도 그건 여전히 "claim 가능한 후보"일 뿐, 승격이
  곧 대본 생성이나 업로드로 자동 이어지지 않는다(기존 계약 그대로: 사람이 claim 버튼을 눌러야
  Stage B가 시작됨).

## 7. 감사 로그

- `topic_research_jobs`가 사실상 잡 단위 감사 로그를 겸함(트리거/상태/실패사유/폴백여부).
- `topic_feedback_events`가 사람의 승인/반려/중복신고 행위를 기록.
- 두 테이블 모두 AIR-0225B 컨벤션(RLS enabled, 정책 없음, service_role 전용)을 따르므로
  Hermes나 일반 사용자가 로그를 조작할 수 없다 — 로그 기록 자체가 `AIR Topic Service`(신뢰
  경계 안쪽)에서만 일어난다.

## 8. 웹어드민 PRO 설정과의 관계 (금지사항 확인)

이번 설계는 `global_settings.sys_api_topic_generation_model` 등 기존 웹어드민 AI 모델 설정을
**읽지도, 대체하지도 않는다** — Hermes 조사는 `topic_research_jobs`라는 완전히 별도 경로이고,
기존 관리자 생성기(`auth-web/app/api/admin/topics-queue/route.ts`)는 그대로 살아있다. PRO용
이미지·영상 모델 설정 제거는 이번 작업 범위에 전혀 포함되지 않았음을 명시적으로 확인한다.

## 9. 잔여 위험 (Go/No-Go 판단 시 함께 고려)

1. **research-context 응답의 "사용 이력 요약"이 여전히 콘텐츠 소재를 담고 있어, Hermes 운영사
   (Nous Research 또는 그 인프라 제공자)에게 우리 콘텐츠 전략 정보가 노출된다.** 이건 원천 차단이
   불가능한 종류의 위험(요약이라도 넘겨야 중복검사가 되므로) — 계약/이용약관 검토가 필요한
   영역이라 CTO 결정 항목으로 남긴다.
2. **PoC 단계 네트워크 비격리**(§5) — 운영 전환 전 반드시 재검토.
3. **자동승격 임계값을 잘못 설정하면 저품질/위험 콘텐츠가 사람 검토 없이 `topics_queue`에
   들어갈 수 있음** — 초기값은 보수적으로(§DATA_MODEL §9) 설정하고, 운영 데이터가 쌓이기 전까지
   전부 관리자 검토를 거치는 것을 권장(§평가 기준 이후 재조정).
