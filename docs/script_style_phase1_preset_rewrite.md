# 1차 핵심 스타일 프리셋 재작성 — 변경 전/후

적용 방법: `db.save_script_style_preset()` (관리자 Settings UI가 호출하는 것과 동일한 함수).
스키마 변경 없음 (기존 `script_style_presets` 테이블의 `prompt_value`/`display_name_ko` 컬럼만 갱신,
`documentary`는 신규 INSERT). 전체 변경 전/후 원문: `scratchpad/style_qa/preset_before_after.json`
(세션 로컬 백업, 롤백 참고용 — 필요 시 이 JSON의 `before` 블록 내용으로 각 키를 되돌릴 수 있다).

## default

**변경 전** (분류: B, 순수 영상미):
> [자연스럽고 선명한 색감], [깨끗하고 투명한 화질], [사실적인 디테일], [풍부한 질감], [자연광], [편안하고 밝은 분위기], [영화 같은 영상미]

**변경 후** (분류: A):
> 서술자 톤: 친근하고 신뢰감 있는 1인칭 나레이터...(10개 항목 전체는 `services/script_style_resolver.py` 실행 결과 또는 Settings UI에서 확인 가능)

## news / story / senior_story / joseon_sageuk / horror_suspense / k_webtoon / sports_analysis

동일한 방식으로 "서술자 톤 / 문장 길이와 리듬 / 어휘 수준 / 대화와 내레이션 비율 / 정보 공개 순서 /
섹션 시작 방식 / 섹션 종료 방식 / 감정 강도 / 피해야 할 표현 / 장르 고유의 전개 규칙" 10개 항목을
전부 포함하도록 재작성했다. 색감/화질/조명/작화 등 순수 시각 묘사는 전부 제거했다.

전체 변경 전/후 원문은 `scratchpad/style_qa/preset_before_after.json` 참고. 요약:

| key | 변경 전 핵심 내용 | 변경 후 핵심 내용 |
|---|---|---|
| news | 앵커 톤/딕션/스튜디오 배경(음성·시각 위주) | 두괄식 보도체, 역피라미드 구조, "~라고 밝혔습니다" 간접화법 |
| story | 할머니 목소리/옛날 소품(음성·시각 위주) | 토속어·구연 리듬, "그런데 말입니다..." 여운, 권선징악 구조 |
| senior_story | 차분한 목소리/삶의 지혜(추상적) | 회고→각성 구조, "돌이켜보면" 문두, 존댓말 고백체 |
| joseon_sageuk | 한옥/궁궐 배경(순수 시각) | 고어체 어미·한자어, "~하오"체 대사, 충효의리 갈등 구조 |
| horror_suspense | 어두운 조명/무서운 괴물(순수 시각) | 정보를 아껴 공개, 클리프행어 종결, 복선→고조→반전 구조 |
| k_webtoon | 트렌디한 그림체/화려한 색감(순수 시각) | 대사 60%+나레이션 40%, 컷 단위 전개, 의성어 강조 |
| sports_analysis | 1줄 영문 요약(내용은 맞으나 항목 누락) | 10개 항목 전체로 보강(캐스터 톤, 통계 인용, 관전 포인트 종결) |

## documentary (신규)

기존 43개 키 목록에 존재하지 않았다. 1차 대상에 포함되어 있어 신규 생성했다
(`display_name_ko`: "다큐멘터리 (Documentary)"). 3인칭 권위 있는 내레이터, 주제-근거-반증-종합
논증 구조로 작성.

## script_master

**변경하지 않음.** 이미 A등급(4단계 딥다이브 대본 빌드업 프로세스, 3,300자 분량의 상세 지침)으로
판단해 1차 대상에서 제외했다. `docs/script_style_preset_audit.md` 참고.

## 실 생성 결과로 확인한 효과

동일 주제/섹션으로 8개 스타일을 실제 Gemini 호출로 비교한 결과(`docs/script_style_qa_results.md`),
정비 전에는 `news`/`k_webtoon`이 `default`와 거의 구분되지 않는 문체를 냈으나, 정비 후에는
8개 전부 사람이 읽었을 때 명확히 구분되는 결과를 얻었다.

## DB 마이그레이션 여부

**불필요.** `script_style_presets` 테이블 스키마(컬럼 구조)는 전혀 바꾸지 않았다. 기존 행의
값만 갱신했거나(9개), 기존 INSERT 경로로 새 행을 추가했다(`documentary` 1개) — 둘 다 이미
존재하는 `db.save_script_style_preset()` 함수 그대로 사용했다.
