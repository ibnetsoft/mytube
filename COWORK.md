# CoWork 실행 안내

이 프로젝트는 CoWork의 로컬 터미널에서 한 편의 콘텐츠를 바로 생성할 수 있습니다.
창작 단계(기획 보강, 대본, 장면별 이미지·영상 프롬프트, 메타데이터)는 Codex 경로로 고정됩니다. 주제 검증은 설정된 YouTube Data API와 웹 리서치 데이터를 사용합니다.

## 시작 전 확인

- `D:\Projects\에어스튜디오\mytube_clone_20260828\.env`에 Supabase, Notion, YouTube Data API 및 Codex 실행에 필요한 키가 설정되어 있어야 합니다.
- 해당 키가 없거나 저장 단계가 실패하면 생성 결과를 성공으로 처리하지 않습니다.
- 이미지 생성·크롭·영상 생성은 이 명령에 포함하지 않습니다. 이미지/영상 **프롬프트**만 산출합니다.

## CoWork에서 실행

CoWork에서 이 프로젝트를 연 뒤, 터미널에서 다음 명령을 실행합니다.

```powershell
Set-Location 'D:\Projects\에어스튜디오\mytube_clone_20260828'
python worker/run_full_autopilot_pipeline.py --category '옛날이야기' --duration 300 --force
```

`--duration 300`은 5분입니다. 옛날이야기 5분 작업은 초반 60초를 5초 장면 12개로, 이후를 15초 장면으로 구성하도록 현재 파이프라인 규칙을 적용합니다.

명령은 로컬 작업 큐와 자동조종기를 함께 시작하고, 완료 시 콘텐츠 ID·오류 여부를 터미널에 표시합니다. 생성 산출물과 저장 상태는 대시보드/DB에서 이어서 확인할 수 있습니다.

## CoWork 이미지 생성·크롭·씬 저장

이미지 생성 API는 사용하지 않습니다. CoWork에서 `$mytube-cowork-scene-assets`를 요청하면, 생성된 2x2 이미지 그리드를 씬별 PNG로 자른 뒤 **1920×1080으로 업스케일**하고, 품질·해상도 확인 후 Supabase Storage 및 `topics_queue`의 해당 씬 URL에 저장합니다. 1~12씬도 정지 이미지를 허용합니다.

이 흐름은 `worker/cowork_scene_assets.py`의 `export → crop → publish` 명령으로 검증·저장되며, 이미지 생성 도구는 CoWork가 각 매니페스트 프롬프트마다 직접 호출합니다.

새 작업은 [이미지 실패·거절 폴백 절차](docs/IMAGE_GENERATION_RECOVERY.md)를 반드시 적용합니다. export가 만든 recovery 상태에서 호출 전 start, 도구 결과, 시각 검수를 기록합니다. 일시 오류만 제한 재시도하며, 품질 불량 그리드는 씬별 이미지로 분리합니다. 안전 거절·원인 불명은 자동 재시도 없이 대안 검토로 넘기고, 성공 이미지와 참조 캐릭터는 보존합니다. 미완료 상태에서는 전체 crop/publish가 차단됩니다. 설치된 구버전 씬 스킬의 단순 그리드 반복 설명보다 이 프로젝트의 실패 처리 지침을 우선합니다.

## After Effects 하이라이트 단계

대본워커는 After Effects가 없어도 실행할 수 있습니다. Codex 콘텐츠 워커는 장면별 `ae_effect_plan`만 생성하고, 실제 AE 합성은 After Effects가 설치된 Windows 렌더 워커가 선택적으로 처리합니다.

- 일반 컷: 기존 FFmpeg 모션/자막/최종 조립 경로를 사용합니다.
- 하이라이트 컷: `ae_effect_plan.enabled=true`인 씬만 AE 워커가 가져가 검기, 안개, 입자, 빛줄기, 왜곡 같은 합성 클립을 만듭니다.
- AE 실패/미설치/미지원 프리셋: `ffmpeg_basic_motion`으로 폴백합니다.

현재 검증된 로컬 AE 경로는 `C:\Program Files\Adobe\Adobe After Effects CS6\Support Files\aerender.exe`입니다. 자세한 운영 계약은 [After Effects Highlight Pipeline](docs/AFTER_EFFECTS_HIGHLIGHT_PIPELINE.md)을 따릅니다.

## CoWork 썸네일 배경 생성·미리보기

Codex 콘텐츠 워커는 대본 완성 뒤 썸네일 문구 3개와 텍스트 없는 16:9 배경 프롬프트를 함께 저장합니다. 해당 토픽의 배경을 만들 때는 다음 순서를 따릅니다.

```powershell
python worker/cowork_thumbnail_asset.py export --topic-id <TOPIC_ID> --out cowork_batches/<TOPIC_ID>/thumbnail.json
```

`thumbnail.json`의 `prompt`로 CoWork 이미지 도구에서 텍스트 없는 16:9 이미지를 생성합니다. 매니페스트의 `output`에는 목표 해상도와 최종 Storage 경로가 함께 들어 있습니다. 생성이 끝나면 선택한 이미지 파일을 아래처럼 저장합니다.

```powershell
python worker/cowork_thumbnail_asset.py publish --topic-id <TOPIC_ID> --manifest cowork_batches/<TOPIC_ID>/thumbnail.json --image <GENERATED_IMAGE_PATH> --create-bucket
```

대본·문구 생성 후 상태는 `ready_for_cowork`가 됩니다. `publish`는 실제 이미지 파일을 1920×1080으로 맞춰 Storage에 저장하고, 완료 상태 및 `thumbnail_bg_url`을 기록합니다. 이미 클레임된 사용자 웹 프로젝트가 있어도 해당 프로젝트의 스냅샷을 함께 갱신하므로, 프로젝트를 새로 열면 썸네일 페이지의 16:9 캔버스가 이 URL을 배경으로 불러오며 Codex가 생성한 문구 후보를 바로 얹어 미리볼 수 있습니다.

## CoWork 나레이션·대사 음성

공식 Vertex AI Gemini TTS 기반 **Voice Studio**를 사용합니다. 목소리 프리셋,
장면별 연기 지시, 구간 재생성, ElevenLabs 대사, 음성 합성을 지원합니다.
사용자의 브라우저 조작이나 수동 파일 첨부는 필요하지 않습니다.
[Voice Studio 설정·실행 안내](docs/VOICE_STUDIO.md)를 따릅니다.
Cloud 프로젝트·인증·크레딧 적용을 확인한 후 `VOICE_STUDIO_ENABLED=1`로
활성화합니다. 이전 브라우저 로그인/확장 초안은 운영 경로에서 제외했습니다.

## 다른 예시

```powershell
python worker/run_full_autopilot_pipeline.py --category '무협' --duration 600 --force
```

도움말:

```powershell
python worker/run_full_autopilot_pipeline.py --help
```
