# 다국어(영어/일본어) 지원 확장 기획서 (Multilingual Expansion Plan)

## 1. 개요 (Overview)
현재 한국어(ko-KR) 최적화 상태인 롱폼/쇼츠 생성 플랫폼을 **영어(English) 및 일본어(Japanese) 등 글로벌 환경**에서 원활하게 동작하도록 확장하기 위한 기술 분석 및 작업 계획서입니다.

핵심 목표는 기획(LLM), 음성(TTS), 자막(Font)의 3요소가 타겟 언어에 맞춰 유기적으로 변경되도록 하는 것입니다.

---

## 2. 주요 작업 영역 (Key Areas)

### A. 데이터베이스 (Database)
현재 `project_settings` 테이블에 `voice_language`가 존재하지만, 기획 단계 전체를 관통하는 명시적인 **콘텐츠 언어 설정**이 필요합니다.

*   **[필수] `projects` 테이블 확장**
    *   `language` 컬럼 추가 (Default: 'ko', Enum: 'ko', 'en', 'ja', 'es', 'vi' 등)
    *   이 값은 프로젝트 생성 시 결정되며, 이후 모든 Generative AI 요청의 기준이 됩니다.

### B. 백엔드 - 프롬프트 엔지니어링 (Prompts)
현재 `services/prompts.py`는 한국어 지시문으로 하드코딩되어 있습니다. 이를 다국어화해야 합니다.

*   **[필수] 프롬프트 템플릿 다국어화**
    *   **문제점**: 시스템 프롬프트가 "당신은 한국의..."로 시작하면, 영어 콘텐츠를 요청해도 한국어 뉘앙스가 섞이거나 번역투가 될 수 있음.
    *   **해결방안**: 
        1. `prompts_en.py`, `prompts_ja.py` 등 언어별 파일 분리 또는
        2. 하나의 프롬프트 안에서 `{instruction_language}` 변수를 받아 지시문 자체를 영어/일본어로 교체.
    *   **대상**: `GEMINI_SCRIPT_STRUCTURE`, `GEMINI_THUMBNAIL_HOOK_TEXT`

### C. 백엔드 - 음성 합성 (TTS)
*   **[필수] TTS 언어 파라미터 동적 연동**
    *   TTS 요청 시 `project.language` 값을 기반으로 Provider(ElevenLabs, Google)에 정확한 `language_code` 전달.
    *   **보이스 프리셋 분리**: 한국어 보이스(Neural2-A)를 영어 텍스트에 쓰면 발음이 깨짐. 언어 선택 시 해당 언어 전용 보이스 목록만 UI에 노출되도록 필터링 로직 구현.

### D. 백엔드 - 자막 및 폰트 (Subtitles & Fonts)
가장 시급한 시각적 문제입니다. 특히 일본어는 전용 폰트가 없으면 한자/가나가 네모 박스(□)로 깨져 보입니다.

*   **[필수] 다국어 폰트 시스템 구축**
    *   언어별 기본 폰트 파일 확보 (`assets/fonts/` 내 구분)
        *   **KO**: 나눔고딕, 프리텐다드 (기존)
        *   **EN**: Roboto, Montserrat, Impact (영어권 선호 굵은 폰트)
        *   **JA**: Noto Sans JP (필수), Kosugi Maru (귀여운 느낌)
    *   `video_service.py` 자막 생성 시 `project.language`에 따라 폰트 경로 자동 스위칭.

---

## 3. 상세 체크리스트 (Action Checklist)

### 단계 1: 데이터 및 설정 (Foundation)
- [ ] **DB 마이그레이션**: `projects` 테이블에 `language` 컬럼 추가.
- [ ] **폰트 확보**: 구글 폰트에서 `Noto Sans data(JP)`, `Roboto(EN)` 다운로드 및 `c:\...\assets\fonts\` 배치.
- [ ] **Config 수정**: `style_presets`에 언어별 기본 폰트 매핑 추가.

### 단계 2: 로직 수정 (Backend)
- [ ] **`main.py` & `projects.py`**: 프로젝트 생성 API (`/api/projects`)에서 `language` 파라미터 수신 및 저장 로직 추가.
- [ ] **`prompts.py`**: 
    - `GEMINI_SCRIPT_STRUCTURE` 프롬프트를 언어 변수에 따라 English/Japanese Instruction으로 바뀌도록 수정.
    - JSON 출력 키값은 영어로 통일하되, 내용(`text`)은 타겟 언어로 나오도록 강제.
- [ ] **`audio_service.py`**: TTS 생성 시 `lang=ja-JP` 등 코드 전달 확인.

### 단계 3: UI/UX (Frontend)
- [ ] **프로젝트 생성 팝업**: "언어 선택" 드롭다운 추가 (🇰🇷 한국어 / 🇺🇸 English / 🇯🇵 日本語).
- [ ] **오토파일럿 UI**: 시작 설정에 "타겟 언어" 옵션 추가.
- [ ] **보이스 선택화면**: 선택된 언어에 맞는 보이스만 필터링하여 보여주기.

---

## 4. 예상 소요 시간 (Estimation)
*   **기본 구조 작업 (DB/Font)**: 2시간
*   **프롬프트 최적화 (EN/JA)**: 3~4시간 (테스트 포함)
*   **UI 및 연동**: 2시간
*   **총 예상 시간**: 약 1일 (M/D 1.0)
