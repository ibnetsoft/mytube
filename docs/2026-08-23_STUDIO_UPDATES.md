# 📢 에어스튜디오 & AIRWorker 일일 업데이트 보고서

- **작성 일자**: 2026년 8월 23일
- **대상 모듈**: AIRWorker (콘텐츠/렌더링 워커), Dashboard (워커 웹 대시보드), TTS/자막 파이프라인
- **주요 목적**: 대화체/짧은 대사 연기력 개선, 화자/지문 자막 노출 방지, 대시보드 설정 UI 고도화, 원클릭 Git 업데이트 추가, 워커 안정성 및 품질 검증 강화

---

## 1. 🎙️ TTS 및 자막 파이프라인 대화체 연기력 & 클렌징 고도화 (3221f36)

### ① 짧은 대사 표현력 및 다이내믹 보이스 세팅
- **대사(따옴표) 감지 연동**: 대본 내 큰따옴표("...") 대사가 감지되면 ElevenLabs 파라미터를 동적으로 조정(stability: 0.28, style: 0.52)하여 밋밋한 나레이션 톤이 아닌 극적인 감정 연기 톤으로 발화하도록 개선.
- **한국어 감정/지문 사전 대폭 확장**:
  - (속삭이듯), (낮은 목소리로), (절규하듯), (울먹이며), (분노하며), (냉소적으로), (다급하게), (한숨) 등 다양한 한국어 지문을 ElevenLabs 감정 태그([whispers], [quietly], [shouts], [sad], [angry], [sigh]) 및 영문 프리프롬프트로 자동 매핑.

### ② 화자명 오독 및 자막 유출 원천 차단
- **TTS 전처리 강화**: (철수), (영희), (시동생) 등 화자 괄호 및 미정의 지문은 TTS 전송 전 완전 삭제하여 음성으로 읽지 않도록 필터링.
- **통합 자막 정제 함수 (clean_subtitle_text) 구축**:
  - 철수: , 나레이터: , 시동생) , (철수), [sad], 【지문】 등 모든 화자 프리픽스와 괄호/마크다운을 100% 제거하여 **영상 자막(SRT/화면 텍스트)에는 순수 대사/나레이션만 노출**되도록 통일.
  - Whisper 정렬, ElevenLabs JSON 정렬, Edge VTT, 스마트 텍스트 분할 등 모든 자막 경로에 적용.

### ③ Hermes 대본 작성 프롬프트 개선
- 1인 나레이션의 서사 흐름은 유지하되, 인물의 직접 대사가 등장할 때는 (감정/연기톤) "대사" 규격으로 작성하도록 지침 강화.

---

## 2. ⚙️ 대시보드 환경설정 및 관리 기능 고도화 (e14d282, 446f041, 687f8a1)

### ① 원클릭 Git 업데이트 (Git Pull & Restart)
- 대시보드 상단 및 설정 모달에 **[최신 버전 업데이트 (Git Pull)]** 원클릭 버튼 탑재.
- 클릭 시 백그라운드에서 최신 코드를 pull하고 프로세스를 안전하게 리로드하는 기능 지원.

### ② Supabase & 인증 설정 UI 추가
- 대시보드 설정 모달에서 Supabase URL 및 Service Role Key를 직접 입력/수정하고 DPAPI로 안전하게 암호화 저장할 수 있도록 지원.

### ③ 워커 프로파일 UI 지원
- content_only (콘텐츠 생성 전용), ull (전체 기능), ender_only (렌더링 전용) 프로파일 전환 및 설정 UI 구축.

---

## 3. 🛡️ 워커 안정성 및 오토파일럿 품질 강화 (5ce1c9, ffb2a9, e42db7e, 01ad7f)

### ① 대본 중복 제거 및 품질 검증 자동 재시도
- 씬 간 중복 문장/반복 표현 감지 및 자동 정제 알고리즘 강화.
- Hermes 대본 품질 게이트 통과 실패 시 오토파일럿이 스스로 프롬프트를 보정하여 자동 재시도하도록 개선.

### ② 비디오 프롬프트 생성 모드 선택 (Basic vs All)
- 비디오 프롬프트 생성 시 초기 12개 씬만 우선 생성하는 Basic 모드와 전체 씬을 생성하는 All 모드 옵션 추가 (파이프라인 테스트 및 리소스 효율화).

### ③ 중단된 작업 재개(Resume) 매칭 로직 개선
- 재부팅 또는 예외 종료 후 작업 재개 시 ideo_title을 기준으로 상태를 정확하게 매합하여 중복 실행 방지.

---

## 4. 🐞 대시보드 UI 및 통신 버그 픽스 (26b6c8c, 447707c, 7fb699)

- **대용량 페이로드 최적화**: /api/jobs API 호출 시 거대한 결과 데이터 필드를 경량화하여 브라우저 메모리 부하 및 응답 지연 해결.
- **JS 중복 변수 선언 수정**: 대시보드 인라인 스크립트의 중복 변수 선언으로 인한 문법 에러 및 렌더링 멈춤 현상 수정.
- **프로세스 카드 UI 정리**: 내부 업데이터(Updater) 카드를 숨겨 직관적인 프로세스 모니터링 환경 제공.

---

## 5. 📋 금일 커밋 히스토리 (2026-08-23)

| 커밋 해시 | 메시지 |
| :--- | :--- |
| 3221f36 | eat(tts/subtitle): improve short dialogue acting and bracket/speaker cleanup |
| e14d282 | eat(settings): add Supabase URL and Service Role Key settings in dashboard |
| 446f041 | eat(worker): add one-click git pull and update UI in dashboard and settings |
| 5ce1c9 | ix(worker): improve script deduplication and autopilot auto-retry on quality check |
| ffb2a9 | eat: add basic vs all mode for video prompt generation (default: basic for first 12 scenes) |
| e42db7e | ix(worker): merge resumed jobs by video title |
| 01ad7f | ix(worker): enforce local content-only pipelines |
| 26b6c8c | ix(dashboard): hide internal updater card from worker process cards |
| 447707c | ix(dashboard): resolve duplicate JS variable declarations causing syntax error |
| 7fb699 | ix(dashboard): optimize api_jobs payload size and declare missing globals |
| 687f8a1 | eat(worker): add worker profile settings UI and fix dashboard env loading |