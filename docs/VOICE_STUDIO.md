# Voice Studio — 상주 워커 음성 제작 모듈

## 실행 경로

Codex 대본 품질 검사 → Voice Studio → Vertex AI Gemini TTS 나레이션 →
ElevenLabs 인물 대사 → 음량/속도 조정 → 구간 합성 → 최종 WAV + 구간 타임라인.
브라우저, Gemini Reader, 새 Chrome 확장 프로그램을 사용하지 않는다.

`services/voice_studio.py`: 음성 공급자·프리셋·파일 캐시·사용량 제한·합성.
`worker/voice_studio_runner.py`: 대본 분리·CLI·상주 워커 연결.
`worker/hermes_worker.py`: 대본 품질 검사 후, 완료 저장 전에 선택적으로 실행.

## Cloud 크레딧 연결

1. 크레딧이 등록된 결제 계정에 연결된 **Google Cloud 프로젝트 ID**를 확인한다.
2. 해당 프로젝트에서 Vertex AI API(`aiplatform.googleapis.com`)를 활성화한다.
3. 워커 실행 계정에 필요한 Vertex AI 호출 권한과 quota project 사용 권한을 설정한다.
4. 공식 Application Default Credentials(ADC) 또는 관리된 서비스 계정 인증을
   워커 PC에 설정한다. 비밀 키를 대화·소스·브라우저 페이지에 붙여넣지 않는다.
   개발용 ADC는 설치된 Google Cloud CLI에서 `gcloud auth application-default login`
   및 `gcloud auth application-default set-quota-project PROJECT_ID`를 사용한다.
5. 프로젝트와 인증 확인 후 짧은 음성을 생성하고, Cloud 결제 내역에서 크레딧
   적용을 확인한다. 그 다음 상주 워커를 활성화한다.

```text
GOOGLE_CLOUD_PROJECT=실제-프로젝트-id
GOOGLE_CLOUD_LOCATION=us-central1
VOICE_STUDIO_ENABLED=1
VOICE_STUDIO_CONFIG=C:/설정폴더/voice-presets.json
```

`GOOGLE_CLOUD_PROJECT`는 프로젝트 표시 이름이나 결제 계정 ID가 아니다.
기존 Gemini API 키로 generativelanguage.googleapis.com을 호출하지 않는다.
Vertex 프로젝트 경로와 `x-goog-user-project`에 동일한 프로젝트를 지정한다.

크레딧 화면만으로 특정 SKU의 실제 차감을 확정하지 않는다. 이 모듈은
Cloud 크레딧 잔액을 실시간으로 읽거나, 다른 서비스 사용액을 차단하지 않는다.
작업의 문자 제한은 생성량 제한이며 금액 상한/초과 과금 방지 보장이 아니다.

## 목소리 설정

워커 대시보드의 **Voice Studio** 메뉴에서 30개 목소리를 성별·이름으로
검색하고 한국어 샘플을 들을 수 있다. 최초 샘플 생성은 실제 Cloud 호출이며,
동일 설정의 샘플은 디스크 캐시를 재사용한다. 샘플은 고정 문장/말투로 비교한다.

저장된 대본을 목록에서 고르면 자동으로 내용을 불러온다. 목소리, 말투, 속도,
대사 처리 방식을 고르고 **이 대본에 목소리 저장**을 누르면
워커 config/voice_studio 아래에 대본별 설정이 저장된다. topic_queue_id가 있는
대본은 같은 topic ID의 이후 Voice Studio 실행에도 해당 설정을 적용한다.
명시적 voice_segments의 다른 프리셋은 유지된다. 저장 자체가 음성을 생성하거나
상주 워커의 자동 생성 기능을 켜지는 않는다.

**선택한 설정으로 음성 생성**은 현재 표시된 대본을 바로 처리하며, 최종 WAV를
재생/다운로드할 수 있다. 화면에서 편집한 대본은 원본 대본을 덮어쓰지 않는다.
음성은 output/voice_library에 보관된다. 한 번에 한 생성 작업만 실행하며,
실패 시 오류를 표시한다. 브라우저를 닫아도 서버 작업은 계속되며, 재시작 후
같은 입력으로 다시 생성하면 완료된 구간을 재사용한다.

2026-09-10 실제 대시보드에서 Kore 한국어 샘플 약 8.8초를 생성/재생했다.
반복 샘플 요청 후 실제 공급자 요청 수가 1회로 유지됨을 확인했다.
개발 소스 대시보드에서 사용 가능하며, 설치형 EXE 재패키징은 별도이다.

```powershell
python -m worker.voice_studio_runner presets --out voice-presets.json
python -m worker.voice_studio_runner check
```

기본 프리셋:

| 이름 | 엔진 | 목소리/용도 |
|---|---|---|
| narrator | Vertex Gemini Flash TTS | Charon, 따뜻하고 절제된 한국어 이야기 |
| narrator_soft | Vertex Gemini Flash TTS | Sulafat, 부드러운 한국어 나레이션 |
| dialogue | ElevenLabs | 기존 TTS 기본 목소리, 인물 대사 |
| dialogue_gemini | Vertex Gemini Flash TTS | Puck, Gemini로 대사도 생성할 때 |

이는 시작용 설정이며 실제 음색/한국어 품질은 청취 후 선택한다. 각 프리셋의
voice, model, language, direction, speed(0.7–1.3), pause_ms(0–2000)를 변경할 수 있다.
speed는 생성된 오디오의 후처리 배속이며 말투 지시와 구별한다.
현재 ElevenLabs 어댑터는 자유문장 direction을 지원하지 않고 오류로 알린다.
Gemini 프리셋과 각 구간의 direction은 자연어로 제어한다.

## 인물별·장면별 설정

가장 정확한 입력은 완성 대본과 명시적 voice_segments다.

```json
{
  "script": "그가 문을 열었다. “누구세요?” 바람이 불었다.",
  "voice_segments": [
    {"id": "scene01_narration", "preset": "narrator", "text": "그가 문을 열었다.", "direction": "낮은 목소리로 긴장감을 조금씩 높이세요."},
    {"id": "scene01_actor", "preset": "dialogue", "text": "누구세요?"},
    {"id": "scene02_narration", "preset": "narrator", "text": "바람이 불었다.", "direction": "차분하게 마무리하세요."}
  ]
}
```

여러 인물은 프리셋을 추가하고 각 구간에서 이름으로 지정한다. 세그먼트 ID를
유지해야 편집 후 다른 구간의 캐시를 재사용하기 쉽다. 자동 분리 모드는
큰따옴표 안을 기본 대사 프리셋으로 처리하며 화자를 추론하지 않는다.
명시적 voice_segments는 권위 있는 음성 원문으로 사용한다. 대본과의 누락/
중복 여부 및 괄호 지문 처리는 호출자가 검증해야 한다. 문장별 음성 인식 QA나
화자 자동 식별을 구현했다고 간주하지 않는다.

```powershell
python -m worker.voice_studio_runner run --package package.json --out output/voice-job
python -m worker.voice_studio_runner run --package package.json --out output/voice-job --regenerate scene01_actor
```

동일 구간은 파일 해시와 생성 설정을 검사해 재사용한다. 텍스트·목소리·연기
지시가 바뀌면 그 구간만 다시 생성한다. `--regenerate`는 변경이 없어도 지정
구간을 다시 생성한다. 이전 파일은 유지한다.

## 저장 및 제한

- 출력: 48 kHz mono PCM16 WAV, 실제 샘플 기준 구간 타임라인.
- 음량: 한 번의 loudnorm 처리로 목표 -18 LUFS, true peak -2 dB 설정.
  발행 기준 충족 여부는 최종 측정이 필요하다.
- 타임라인은 구간 단위다. 단어별 자막 정렬은 아직 포함하지 않는다.
- 기본 작업 제한: Vertex 30,000자(대본+연기 지시), ElevenLabs 3,000자.
  토큰 과금과 문자 수는 동일하지 않다. 제한은 설정 파일에서 조정한다.
- 시간 초과도 요청 횟수/문자 예약에 남기고 자동 유료 재호출하지 않는다.
- 로그인이나 크레딧 부족을 이유로 다른 유료 공급자로 자동 전환하지 않는다.
- 1구간 최대 1,200자. 자동 분리는 문장/공백 경계를 우선한다.

## 검증 상태

공식 REST 요청의 프로젝트/음성 설정, PCM 포맷 검사, 잘린 응답 거부,
실제 FFmpeg 변환·합성, 캐시 재사용, 구간 재생성, 사용량 제한을 테스트했다.
2026-09-10 프로젝트 `secret-well-480907-a4`의 사용자 ADC 인증으로 실제
Vertex Gemini Flash TTS 호출에 성공했다. Charon 한국어 샘플은 약 9.73초이며,
48 kHz mono WAV 정규화와 저장까지 완료했다. 출력은
`output/voice_studio_cloud_probe_20260910/voice-studio.json`에 기록했다.
응답 사용량은 입력 95토큰, 출력 오디오 243토큰이다.
Cloud Billing 조회는 HTTP 403으로 실패하여 크레딧 차감은 미확인이다.
현재 설치형 워커 업데이트와 전체 자동 파이프라인 실운영 검증은 아직 미완료다.

공식 근거:
- https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
- https://developers.google.com/profile/help/benefits
