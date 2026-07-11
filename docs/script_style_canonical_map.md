# script_style canonical key / alias 정책

## 배경

`script_style_presets` 테이블에는 여러 세대에 걸쳐 동일한 내용이 서로 다른 키 이름으로
중복 저장된 항목이 10쌍 있다. 기존에 저장된 프로젝트(`project_settings.script_style`)나
`topics_queue.assigned_script_style` 행이 어느 쪽 키를 참조하고 있었는지 알 수 없으므로,
DB에서 레거시 키를 삭제하거나 강제로 재작성하지 않고 **resolver 레벨의 별칭 변환**으로
해결했다.

## canonical 선정 기준

`auth-web/app/api/admin/topics-queue/route.ts`의 `SCRIPT_STYLE_KEYS` 허용목록(웹어드민이
AI 자동 주제 생성 시 실제로 선택 가능한 26개 키)에 포함된 쪽을 canonical로,
포함되지 않은 쪽을 레거시 별칭으로 지정했다. 이 목록은 시스템에서 "현재 실제로
노출·사용 중인 키"를 나타내는 가장 신뢰할 수 있는 근거이기 때문이다.

## canonical / alias 매핑 표

| canonical key | 레거시 alias key | SCRIPT_STYLE_KEYS 포함 여부(canonical) | 비고 |
|---|---|---|---|
| joseon_sageuk | joseon_drama | 포함 | 조선시대 사극 |
| north_korean_drama | north_korea_drama | 포함 | 북한 드라마 |
| silent_20s | silent_film_20s | 포함 | 20년대 무성영화 |
| k_manhwa | k_comics | 포함 | K만화 |
| cute_animal_char | cute_animal | 포함 | 귀여운 동물 캐릭터 |
| neonsign_citypop | neon_citypop | 포함 | 네온사인 시티팝 |
| graphite_sketch | pencil_sketch | 포함 | 연필 스케치 |
| renaissance_sacred | renaissance_religious | 포함 | 르네상스 종교화 |
| bgm | bgm_focus | 포함 | 배경음악 중심 |
| story | old_story | 포함 | 옛날 이야기 |

`basic`/`script_master`는 이번 alias map에 포함하지 않았다 (내용은 사실상 중복이지만
과제에서 지정한 10쌍 범위를 벗어나며, 웹어드민 `SCRIPT_STYLE_KEYS`에도 둘 다 없어
canonical 판단 근거가 약함 — 별도 논의 후 결정 권장. `docs/script_style_preset_audit.md`의
F 등급 참고).

## 구현 위치

`services/script_style_resolver.py`의 `_ALIAS_MAP` 딕셔너리(레거시 키 → canonical 키).
`resolve_script_style_directive()`는 다음 순서로 동작한다.

1. 입력값을 정규화(trim + lowercase).
2. `_ALIAS_MAP`에 있으면 canonical 키로 치환.
3. canonical 키로 `script_style_presets`를 조회해 지침을 구성.

레거시 키(`joseon_drama` 등)가 DB에 그대로 남아있어도, 실제 지침 내용은 항상
canonical 키(`joseon_sageuk`)의 최신 내용을 사용한다 — **레거시 행 자체는 이제
읽히지 않는다** (아래 "잔여 위험" 참고).

## 로깅

`_log()`가 `requested_style`(호출부가 실제로 전달한 원본 키)과 `resolved_style`
(alias 변환 후 실제 사용된 canonical 키, 또는 "default")을 분리해서 기록한다.
예: `requested_style=joseon_drama resolved_style=joseon_sageuk fallback_used=False db_error=False`.

## 하위 호환성

- 기존 프로젝트/topics_queue 행이 레거시 키(`joseon_drama` 등)를 참조하고 있어도
  `resolve_script_style_directive("joseon_drama")`는 정상적으로 canonical(`joseon_sageuk`)의
  최신 지침을 반환한다 — 동적 테스트 `test_alias_key_works_even_when_legacy_row_missing_from_db`,
  `test_legacy_alias_key_resolves_to_canonical_preset_content`로 검증.
- DB의 레거시 키 row 자체는 삭제하지 않았다.

## 잔여 위험 (후속 UI 작업 필요)

- **웹어드민 Settings > 대본 스타일 프롬프트 설정 화면은 canonical/alias를 구분하지 않고
  43개 키를 전부 나열한다.** 관리자가 레거시 키(예: `joseon_drama`)의 텍스트를 수정하고
  저장해도, resolver는 이제 그 내용을 전혀 읽지 않으므로 **변경이 조용히 무시된다.**
  화면에는 "저장되었습니다" 성공 토스트가 뜨지만 실제 생성 결과에는 아무 영향이 없다.
  이는 이번 작업 범위(UI 대개편 금지)를 벗어나 있어 코드는 손대지 않았고, 아래 두 가지
  중 하나를 후속 작업으로 제안한다.
  1. 목록 UI에서 레거시 alias 키를 숨기거나 "canonical 키로 자동 통합됨" 배지를 표시.
  2. `/api/settings/script-style-presets` GET이 alias 키를 응답에서 제외(또는 읽기 전용으로
     표시)하도록 서버 측 필터링 추가.
- `SCRIPT_STYLE_KEYS`(웹어드민 AI 자동 주제 생성 허용목록)는 이미 canonical 키만 사용하고
  있어 신규 생성 경로에는 영향이 없다.
