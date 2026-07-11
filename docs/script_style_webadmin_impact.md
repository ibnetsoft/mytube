# 웹어드민(데스크톱 앱 Settings) 영향 분석

**대상 화면**: 데스크톱 앱 `templates/pages/settings.html`의 "대본 스타일 프롬프트 설정"
(`static/js/settings_page.js`의 `loadScriptStylePresets`/`saveOneScriptStylePreset`,
API: `GET/POST /api/settings/script-style-presets`).

이번 작업에서는 이 화면의 코드를 변경하지 않았다 — 읽기 전용 분석만 수행했다.

## 1. 관리자가 실제 AI writing directive를 편집할 수 있는가

**가능하다.** `saveOneScriptStylePreset(key)`가 textarea의 자유 텍스트를
`{style_key, prompt_value}`로 그대로 POST하고, 서버는 `db.save_script_style_preset()`으로
저장한다. 형식 제약이 없어 관리자가 이번에 작성한 것과 같은 "서술자 톤/문장 리듬/..." 형태의
글쓰기 지침을 그대로 입력할 수 있다.

## 2. 필드명/화면 설명이 "영상 스타일"로 오해되게 되어 있는가

**아니오, UI 문구 자체는 이미 정확하다.** 화면 하단 안내문(`settings.html` 728~732줄)이
"대본 생성 시 각 스타일별로 AI에게 전달될 작성 지침입니다"라고 명시하고 있어, 문구만 보면
글쓰기 지침이라는 것이 분명하다. **문제는 UI가 아니라 데이터였다** — 라벨은 "작성 지침"이라고
말하면서 실제 저장된 43개 중 대다수의 내용은 색감/조명/작화 같은 시각 연출 묘사였다
(`docs/script_style_preset_audit.md`의 B/C 등급 참고). 이번 작업의 1차 정비는 데이터를
UI가 원래 약속한 내용에 맞게 고친 것이다.

## 3. canonical key와 alias key가 모두 중복 노출되는가

**그렇다.** `loadScriptStylePresets()`는 `/api/settings/script-style-presets?detailed=true`가
반환하는 모든 키를 `Object.entries()`로 순회해 카드로 렌더링한다. 이 엔드포인트는
`db.get_script_style_presets_detailed()`를 그대로 반환하므로, `joseon_sageuk`와
`joseon_drama`처럼 canonical/alias 쌍이 **서로 무관한 두 개의 별개 카드처럼** 화면에 나온다.

**중요한 부작용**: `services/script_style_resolver.py`의 alias map 도입 이후, 관리자가
alias 키(예: `joseon_drama`)의 카드를 열어 내용을 수정하고 저장해도 "저장되었습니다" 토스트는
뜨지만 **실제 생성 결과에는 전혀 반영되지 않는다** (resolver가 canonical 키의 값만 읽기
때문). 이는 관리자 입장에서 원인을 알 수 없는 "설정이 안 먹힌다" 문의로 이어질 수 있는
잠재적 위험이다. `docs/script_style_canonical_map.md`의 "잔여 위험" 항목에 후속 UI
개선안(레거시 키 숨김 또는 읽기 전용 배지)을 제안해 두었다.

## 4. 빈 프리셋을 저장할 수 있는가

**가능하다.** `saveOneScriptStylePreset`은 textarea 값이 빈 문자열이어도 그대로 POST하며,
서버(`save_script_style_preset_api` → `db.save_script_style_preset`)에도 빈 값 검증이
없다. 다만 이번 resolver 정책 변경으로 인해 **결과가 안전하게 저하되도록**은 되어 있다 —
빈 prompt_value는 resolver가 "비활성"으로 간주해 자동으로 default 지침으로 폴백하므로,
관리자가 실수로 특정 스타일을 비워도 생성 자체가 깨지지는 않는다. 다만 그 스타일을 선택한
프로젝트가 조용히 default 문체로 바뀌는 것 자체는 여전히 관리자에게 알려주는 것이 좋다 —
저장 시 "이 스타일은 비어 있어 기본 스타일로 대체됩니다" 같은 경고 UI를 추가하는 것을
후속 과제로 제안한다.

## 5. 프리셋 미리보기/테스트 생성 기능이 필요한가

**필요하다고 판단한다.** 현재는 관리자가 프리셋을 수정한 뒤 실제 효과를 확인하려면 대본
기획→생성 전체 플로우를 거쳐야 한다. 이는 정확히 이번 작업의 발단이 된 문제
("스타일이 다 똑같아 보인다"는 사용자 신고가 실제 원인 파악까지 오래 걸렸던 이유 중 하나)와
같은 종류의 재발 위험을 남긴다. "이 스타일로 샘플 생성" 버튼 하나로 짧은 샘플 문단을
즉시 생성해 보여주는 기능을 추가하면, 향후 프리셋을 고칠 때마다 이번처럼 별도 QA 스크립트를
작성하지 않고도 관리자가 스스로 검증할 수 있다.

## 이번 작업에서 UI를 변경하지 않은 이유

과제 지시에 따라 이번 라운드에서는 대규모 UI 개편을 하지 않았다. 위 5개 항목은 모두
**읽기 전용 분석 결과이며, 실제 코드 변경은 수행하지 않았다.** 후속 UI 변경안은 우선순위
순으로 다음과 같이 제안한다.

1. alias 키를 목록에서 숨기거나 "canonical로 자동 통합됨" 표시 (편집이 무시되는 혼란 방지 — 가장 시급).
2. 빈 프리셋 저장 시 경고 표시.
3. "샘플 생성" 미리보기 버튼 추가.
