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

## CoWork 썸네일 배경 생성·미리보기

Codex 콘텐츠 워커는 대본 완성 뒤 썸네일 문구 3개와 텍스트 없는 16:9 배경 프롬프트를 함께 저장합니다. 해당 토픽의 배경을 만들 때는 다음 순서를 따릅니다.

```powershell
python worker/cowork_thumbnail_asset.py export --topic-id <TOPIC_ID> --out cowork_batches/<TOPIC_ID>/thumbnail.json
```

`thumbnail.json`의 `prompt`로 CoWork 이미지 도구에서 텍스트 없는 16:9 이미지를 생성하고, 선택한 이미지 파일을 아래처럼 저장합니다.

```powershell
python worker/cowork_thumbnail_asset.py publish --topic-id <TOPIC_ID> --image <GENERATED_IMAGE_PATH> --create-bucket
```

`publish`는 이미지를 1920×1080으로 맞춰 Storage에 저장하고 `thumbnail_bg_url`을 기록합니다. 프로젝트를 열면 썸네일 페이지의 16:9 캔버스가 이 URL을 배경으로 불러오며, Codex가 생성한 문구 후보를 바로 얹어 미리볼 수 있습니다.

## 다른 예시

```powershell
python worker/run_full_autopilot_pipeline.py --category '무협' --duration 600 --force
```

도움말:

```powershell
python worker/run_full_autopilot_pipeline.py --help
```
