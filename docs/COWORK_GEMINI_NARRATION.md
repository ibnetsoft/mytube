# Codex/CoWork 브라우저 나레이션 단계

## 현재 차단 사항 — 2026-09-10

실제 전용 Playwright Chrome의 Google 로그인이 `signin/rejected` 및
“브라우저 또는 앱이 안전하지 않을 수 있습니다”로 거부됐다. setup 명령은
같은 로그인 시도를 반복하지 않도록 중단 처리했다. 아래 최초 로그인 방식은
실패한 설계 기록이며 실행 지침으로 사용하지 않는다. 자동화 탐지 은폐,
쿠키 복사, 계정 보안 약화로 우회하지 않는다.

기존 Chrome + Gemini Reader의 5.16초 파일 생성/저장만 실검증됐다.
상주 워커 연결 코드는 초안이며 운영 활성화/배포하지 않았다. 기존에 인증된
브라우저를 지원되는 방식으로 상주 워커에 연결하는 경로는 아직 미검증이다.

별도 AIR Chrome 확장은 사용하지 않는다. 로그인된 Chrome과 이미 설치된
Gemini Reader를 Codex 브라우저 도구로 조작한다. 사용자에게 대본/음성 파일을
다운로드해서 첨부하도록 요구하지 않는다. 브라우저 작업과 로컬 파일 처리를
에이전트가 연속으로 수행한다.

## 상주 워커 연결 (직접 Gemini 웹, 새 확장 없음)

`worker/gemini_web_narration.py`가 전용 Chrome 프로필을 열고 나레이션 원문
확인 → 듣기 → 단일 오디오 Blob 확보 → WAV 검증 → ElevenLabs 대사 → 결합을
실행한다. `hermes_worker.py`의 Codex 콘텐츠 품질 검사 직후에 연결했다.
대본 체크포인트는 음성 처리 전에 저장하므로 음성 실패 후 수동 대본 재생성이
필요하지 않다. 아래 설정을 활성화한 작업만 음성 단계를 실행한다.

```powershell
python -m pip install -r worker/requirements-gemini-browser.txt
python -m worker.gemini_web_narration setup
```

전용 Chrome에서 최초 Google 로그인을 완료하고 창을 닫는다. 기존 Chrome
쿠키는 복사하지 않는다. 다음 환경 설정을 워커에 적용하고 재시작한다.

```text
GEMINI_WEB_NARRATION_ENABLED=1
GEMINI_DIALOGUE_VOICE_ID=<사용할 ElevenLabs 보이스 ID>
```

기본 분리는 쌍을 이루는 큰따옴표/곡선 큰따옴표를 대사로 취급한다. 여러
인물 목소리는 명시적 `audio_segments`와 각각의 `voice_id`를 사용한다.
단일 Blob/data 오디오 외 WebAudio/분할 스트림은 아직 지원하지 않으며
명시적으로 실패한다. 이 직접 확보 경로는 전용 프로필 로그인 후 실검증이
필요하다. 기존 Gemini Reader에서 확인한 다운로드 성공과 구별해야 한다.
현재 실행 중인 설치형 워커 바이너리는 아직 재빌드/배포하지 않았다.

일반 `codex exec`가 이 대화의 브라우저 도구를 상속한다고 가정하지 않는다.
브라우저 제어는 워커의 별도 Playwright 모듈이 맡는다. 아래는 이미 검증한
Codex 대화의 Gemini Reader 경로이며 진단/샘플 생성에 사용할 수 있다.

## 에이전트 실행 순서

1. 원본 대본을 순서대로 `kind=narration|dialogue`, `text`, 대사의 `voice_id`로
   구분한다. 화자를 추측하지 않는다. 긴 나레이션은 문장 경계에서 2,000자
   이하로 나눈다. 원문 누락/중복 여부를 확인한다.
2. `worker/cowork_narration.py prepare --segments <JSON> --directory <새 작업 폴더>`.
3. Gemini Reader의 Type or Paste Text → Title/Text → Submit → Download를
   브라우저 도구로 실행한다. 제목에 작업/세그먼트 식별자를 사용한다.
   매 단계 현재 화면을 읽고 진행하며, 실제 성공한 한국어 UI 흐름을 따른다.
4. 100% 생성 완료와 원문 미리보기를 확인한다. 필요하면 Download 버튼을
   누른다. 정확히 이 작업으로 생성된 파일만 가져온다. 다운로드 폴더의
   '최신 파일'을 무조건 선택하지 않는다. 임시 확장자는 성공 근거가 아니며,
   내용 디코드와 파일 안정성을 확인한다. 파일이 불명확하면 자동 실패한다.
5. `accept --manifest <경로> --segment <ID> --source <파일>`로 48 kHz mono WAV로
   디코드하고 길이/해시/파일을 기록한다. 원본 다운로드는 삭제하지 않는다.
6. 모든 나레이션 확보 후 `dialogue --manifest <경로>`로 대사만 기존
   ElevenLabs 서비스에서 생성한다. 생성 비용이 드는 실제 실행은 사용자
   요청 범위에 포함됐는지 확인한다. 나레이션을 유료 API로 대체하지 않는다.
7. `assemble --manifest <경로>`로 순서대로 결합한다. 매니페스트의 timeline은
   실제 PCM 샘플 기준 구간 시작/끝이다. 단어별 자막 정렬·음량 평준화는
   별도 단계이며 이 명령에서 수행했다고 보고하지 않는다.

## 2026-09-10 검증

연결된 Chrome에서 한국어 시험 텍스트를 자동 입력하고 Gemini Reader가
Download Complete (100%)까지 도달한 것을 확인했다. 다운로드 산출물을
FFprobe로 검사해 MP3 / 48 kHz / mono / 5.16초임을 확인했다.
전체 대본 배치, 실제 유료 대사 생성, 전용 프로필을 통한 상주 직접 음성 확보는 미검증이다.
