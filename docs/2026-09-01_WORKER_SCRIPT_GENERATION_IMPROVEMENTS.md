# 워커 대본 생성 파이프라인 점검 및 보완 보고서

- **작성 일자**: 2026년 9월 1일
- **대상 모듈**: `worker/hermes_worker.py`, `worker/hermes_autopilot.py`
- **주요 목적**: 워커 대본 생성(Script Generation) 파이프라인 분석, 품질 게이트 판정 결함 수정, 다국어(CJK) 문자 유실 방지, 페이스/모델 분리 및 카테고리별 맞춤 개선

---

## 1. 개요 및 파이프라인 흐름

현재 워커 시스템의 대본 생성 파이프라인은 다음과 같이 다단계로 동작합니다:

1. **`script_plan_generate`**: 카테고리별 스타일, 러닝 프로파일, 품질 피드백을 반영하여 씬 구조(`structure`, `scenes[]`) 기획
2. **`script_generate`**:
   - 내러티브 블루프린트(`_generate_narrative_blueprint`) 및 주인공/조연 앵커 생성
   - 씬 청크 분할 및 초안 생성 (`draft_model`)
   - AI 품질 검사(`_evaluate_script_quality`) → 미달 시 전체 리라이트(`_revise_full_script`)
   - 언어 적합성 검사(한국어 라틴문자 이탈, 일본어 한글 이탈) → 필요 시 언어 강제 리라이트
   - 문장 중복 검사 및 정제
3. **`publish_metadata_generate`**: 대본 기반 YouTube 제목/설명/태그 생성
4. **`validate_generation_package`**: 전체 패키지 최종 품질 게이트 검증 후 Supabase `topics_queue`에 `ready` 상태 동기화

---

## 2. 주요 결함 수정 내역

### 2-1. 대본 리라이트 판정 규칙 확인 (`hermes_worker.py`)
- `_script_needs_revision()`은 기존부터 `verdict != "pass"`, `score < 78`, `critical_issues` 중 하나라도 충족하면 리라이트를 요청했습니다.
- 이번 변경에서는 사람이 명시적으로 승인한 `verdict == "manual_override"`만 리라이트 대상에서 제외했습니다. 일반 `revise` 판정은 계속 리라이트됩니다.

### 2-2. 🔴 QA 통과 점수 기준 일관화 (`hermes_worker.py`)
- **기존 문제**: Fallback QA 보고서(`_fallback_script_quality_report`)의 통과 기준은 `score >= 72`였으나, 실제 AI QA 및 게이트 기준은 `score >= 78`을 요구하여 불일치가 발생했습니다.
- **수정 내용**: Fallback QA 통과 기준 점수를 `78`점으로 통일하여 일관성을 확보했습니다.

### 2-3. 🔴 다국어(일본어/CJK) 대본 정제 시 문자 유실 수정 (`hermes_worker.py`)
- **기존 문제**: 대본 정제 정규식 `_CLEANUP_ALLOWED_PATTERN`이 한글/영문/기본 기호만 포함하고 있어, 일본어 대본 정제 시 히라가나, 가타카나, 한자 및 CJK 부호(`「`, `」`, `、`, `。`)가 삭제/훼손되는 문제가 있었습니다.
- **수정 내용**: CJK 유니코드 범위(`\u3040-\u309F`, `\u30A0-\u30FF`, `\u4E00-\u9FFF`, `\u3000-\u303F`, `\uFF00-\uFFEF`)를 패턴에 추가하여 다국어 대본의 문자 유실을 원천 차단했습니다.

### 2-4. 🟠 문장 중복 제거(`_deduplicate_script_text`) 오분리 방지 (`hermes_worker.py`)
- **기존 문제**: 문장 분리 정규식 `(?<=[다요죠까])\s+`가 `바다 `, `타다 ` 등 일반 단어 끝의 글자까지 문장 끝으로 인식하여 정상 문장을 훼손했습니다.
- **수정 내용**: 문장 부호(`[.!?。！？]`) 기반 정밀 분리로 변경하고, 중복으로 감지된 특정 문장 세트(`repeated_sentences`)를 우선 필터링하도록 개선했습니다. Python 정규식의 고정 길이 lookbehind 제약을 준수하도록 구현했습니다.

### 2-5. 🟠 구제 대본(Rescue Script) 문장 반복 패딩 개선 (`hermes_worker.py`)
- **기존 문제**: 최소 글자수 미달 시 1개 동일 문장을 무한 반복 덧붙여 문장 중복 감지에 걸릴 위험이 있었습니다.
- **수정 내용**: 한국어/일본어 구제 대본 확장 시 다양한 문맥 확장 단락과 순번을 적용합니다. 임의의 반복 횟수 상한 없이 요청된 최소 글자수를 충족합니다.

### 2-6. 🟠 Autopilot 나레이션 페이스(`narration_pace`) 연동 (`hermes_autopilot.py`)
- **기존 문제**: Autopilot 파이프라인에서 `narration_pace`가 누락되어 카테고리별 설정과 무관하게 항상 기본 속도로만 대본 분량이 산정되었습니다.
- **수정 내용**: `_narration_pace_for_category()` 헬퍼를 신설하고 `script_plan_generate`, `script_generate`, 재개(resume) payload에 정상 전달되도록 연동했습니다.

### 2-7. 🟠 대본 초안 모델 분리 설정 활성화 (`hermes_worker.py`)
- **기존 문제**: `_select_script_draft_model()`이 환경 설정과 무관하게 `final_model`만 반환하여 비용 최적화(초안 모델 분리)가 비활성 상태였습니다.
- **수정 내용**: `config.SCRIPT_DRAFT_MODEL` 또는 환경 변수 `SCRIPT_DRAFT_MODEL`을 우선 조회하여 초안 모델과 QA/리라이트 모델을 분리할 수 있도록 개선했습니다.

### 2-8. 🟡 SFX 큐 역직렬화 안정성 강화 (`hermes_autopilot.py`)
- **수정 내용**: `sfx_cues`가 문자열로 넘어올 경우 자동 JSON 파싱 및 중복 직렬화를 방지하는 안전장치를 추가했습니다.

---

## 3. 기능 확장 및 맞춤형 보완

### 3-1. 카테고리별 재시도(Retry) 가드 세분화 (`hermes_worker.py`)
- QA 실패 후 재시도 프롬프트 작성 시, 이전에는 금융 룰이 일괄 적용되던 문제를 해결하고 카테고리별 전용 가드로 분기했습니다:
  - **금융/연금**: 금액/연금 수치 중복 언급 금지 및 강의식 어조 배제
  - **옛날이야기**: 조선/전근대 설화 세계관 엄수 및 현대 어휘·법률 분쟁 유입 금지
  - **기타 장르**: 장르 외 서브플롯 배제 및 카테고리 세계관/주제 약속 유지

### 3-2. 대본 언어 통계(`language_stats`) 메타데이터 로깅 (`hermes_worker.py`, `hermes_autopilot.py`)
- 대본 생성 완료 시 한글, 영문(라틴), 숫자, 특수문자 비율을 분석한 `language_stats`를 생성 결과 및 Supabase 요약 페이로드에 포함하여 품질 모니터링이 가능하도록 개선했습니다.

---

## 4. 검증 결과

- `worker/hermes_worker.py`: Python 구문 검사 및 컴파일 (`py_compile`) 정상 통과
- `worker/hermes_autopilot.py`: Python 구문 검사 및 컴파일 (`py_compile`) 정상 통과
