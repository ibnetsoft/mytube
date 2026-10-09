# 통합워커 AE 입모양 실행 연결 — 2026-10-09

## 실행 경로와 이전 감사 정정

현재 권장 소스 실행 경로는 다음과 같다.

```text
python -m worker.launch --role local
  → worker.local_media_supervisor
  → ae 역할 (기본 큐 조회)
  → ae_mouth_worker.py --once --mouth-only
  → std_project_assets.metadata.kind = ae_mouth_job
```

`local_media_supervisor`에는 이미 `ae` 역할이 있었다. 이전 프로젝트 3373 감사는 `manager.py`의 프로세스 목록만 확인하여 이 경로까지 입모양 수신기가 없다고 일반화했다. 그 결론은 정정한다. 기존 입모양 CLI는 좌표 분석 작업을 먼저 가져왔고, 해당 작업이 있으면 `--once` 실행에서 정작 입모양 큐를 처리하지 않을 수 있었다. 이번 변경은 AE 역할을 `--mouth-only`로 명시하여 이 우회를 없앤다. 선택적 좌표 분석은 별도 `coordinates` 역할이 담당한다.

별도 관리자 진입점 `air_worker_entry.py --role manager`에도 `ae_mouth_worker`를 등록했다. `full`, `render_only` 프로필에서 자동 시작하며 `content_only`에는 추가하지 않았다. 현재 권장 로컬 미디어 supervisor와 이 관리자를 같은 컴퓨터에서 중복 실행하지 않는다.

## 이번 변경

- AE 큐의 `queued`, `direction_approved`, 2분 이상 갱신되지 않은 `processing` 작업을 조회한다. 작업 점유는 `updated_at` 비교 후 저장하며, 소유 토큰으로 제한한 DB heartbeat를 15초마다 갱신한다. 다른 컴퓨터가 처리 중인 작업은 가져오지 않는다.
- 로컬 상태 파일은 렌더 중에도 3초마다 갱신한다. PID, 작업 ID, 씬 번호, 단계, 처리 결과 수에 따른 진행률, 오류를 기록한다. 진행률은 씬 결과 저장 비율이며 Adobe 인코딩 백분율은 아니다.
- 관리자 시작·중지·재시작·로그·상태·미디어 종료 대기·작업 중 Hermes 일시정지에 연결했다. 인증된 로컬 API와 관리자 화면에도 시작/중지 경로를 추가했다.
- 작업 결과를 씬마다 저장한다. 관리자 종료 요청은 현재 씬을 마친 뒤 다음 씬 전에 멈추며, 재시작 후 저장된 결과를 재사용한다. 중단된 DB 점유는 최대 약 2분 뒤 재획득할 수 있다. 현재 권장 supervisor는 기존처럼 실행 중인 자식 작업이 끝나기를 기다린다.
- Python 입력 재검증은 활성 에셋을 500개씩 끝까지 읽고 `created_at DESC, id DESC` 순서를 유지한다. 페이지 조회 실패는 불완전한 자료로 처리하지 않는다.
- 최종 렌더 연결 스크립트 `scripts/std_continue_submission.cjs`도 웹의 `loadStdProjectAssets()`를 사용한다. 웹 접수·워커 재검증·최종 렌더 연결 모두 원본 에셋이 1,000개 뒤에 있어도 읽는다.
- 좌표를 나중에 저장한 씬은 재제출 시 해당 씬만 다시 준비한다. 이미 준비된 다른 씬 결과는 유지한다. 최종 렌더가 이미 등록된 작업은 이 방식으로 다시 열지 않는다.

## 1~18번 영상 씬과 건너뛰기 규칙

입력 버전 2는 1~18번 중 저장된 자막에 실제 대사가 있고 원본 영상이 있는 씬을 포함한다. 19번 이후의 기존 이미지 처리도 유지한다.

| 입력 상태 | 처리 |
|---|---|
| 원본 영상 + 유효한 저장 좌표 | 기준 이미지에서 얼굴·입을 확인하고 영상의 위치·크기·회전을 추적하여 입모양 작업 |
| 원본 이미지 + 유효한 저장 좌표 | 기존 이미지 기반 입모양 작업 |
| 기준 이미지 없음 | `skipped`, `skip_reason=missing_reference_image` 저장 후 다음 씬 |
| 화자의 저장 좌표·필수 영역·원본 해시 없음 | `skipped`, `skip_reason=missing_speaker_coordinates` 저장 후 다음 씬 |
| 모든 화자가 화면 밖 | 입모양 작업 없이 건너뜀 |
| 저장 좌표와 원본 해시 불일치, 낮은 신뢰도, 영상 추적 실패 | `needs_review`로 사유를 남김. 잘못된 위치를 임의로 작업하지 않음 |

출력은 확정 TTS 시간을 유지하며 `source_audio_id`, `source_image_id`, 영상인 경우 `source_video_id`, 추적 정보, 렌더 해시, `timing_locked`를 저장한다. 생성 결과는 `review_pending`이며, 검수된 결과만 최종 렌더에 사용한다. 건너뛴 씬은 원본 미디어로 유지한다. 입모양이 없는 씬을 입모양 작업 완료로 표시하지 않는다.

프로젝트 3373의 직전 DB 감사에서는 대사 영상이 **5·12·13·16번**이고 네 씬 모두 저장 좌표가 없었다. 그 상태 그대로 실행하면 네 씬을 건너뛴다. 5·12번은 기준 이미지도 없었다. 영상 입모양 작업을 원하면 원본 영상과 맞는 기준 이미지 및 화자 얼굴·입 좌표를 먼저 저장해야 한다. 이번 작업에서 좌표를 추측하거나 DB 작업을 임의 승인하지 않았다.

## Windows 소스 워커 적용

웹 배포는 Windows의 실행 중인 Python 소스를 갱신하지 않는다. 이 세션에서는 해당 컴퓨터의 실행 상태·설치 경로·Adobe 렌더를 직접 확인하지 않았다.

1. 기존 supervisor에서 진행 중인 작업이 끝나도록 정상 종료하고 상태가 `stopped`인지 확인한다.
2. 실제 워커 소스 폴더에서 `git status`로 로컬 변경을 확인·보존한 후 `git fetch origin`, `git merge --ff-only origin/main`으로 갱신한다. 분기된 경우 강제로 덮어쓰지 않는다.
3. 기존 Python 환경과 연결 설정을 사용하여 사전 점검한다.

```powershell
python -m worker.local_media_supervisor --stop
python -m worker.local_media_supervisor --status
# stopped 확인 후 소스 갱신
python -m worker.launch --role local --env-file worker/connection.env --check
python -m worker.launch --role local --env-file worker/connection.env
```

`--check`는 AE 실행 파일, FFmpeg, 입모양·영상 추적 모듈, DB 설정, Codex CLI 설치를 확인한다. DB 접속 성공이나 Codex 로그인 자체를 보증하지 않으므로 기존 인증도 유지해야 한다. 이미 supervisor가 실행 중이면 입모양 프로세스를 따로 중복 실행하지 않는다. 설치 패키지나 Windows 릴리스는 만들지 않았다.

상태 화면은 `http://127.0.0.1:3004`. supervisor의 `active.role=ae`, `logs/local-media/ae.log`, `logs/ae_mouth_worker.log`, `state/ae_mouth_worker.json` 및 DB의 작업 `state/results`를 함께 확인한다. 실제 경로는 `AIRWORKER_HOME` 설정을 따른다.

## 검증 결과와 한계

- Python 관련 테스트 48개 통과: 기본 역할 선택, 명시적 mouth-only 실행, 전체 자료 조회, heartbeat, 단일 실행 잠금, 씬 종료 대기, 중단 후 결과 재사용, 영상 추적, 타이밍, 좌표 누락 후 다음 영상 씬 처리.
- 웹 관련 테스트 29개 통과: 접수·재제출·검수·대용량 에셋 조회·좌표 추가 후 부분 재개.
- Next.js production build 통과. 저장소 설정은 전체 TypeScript/lint 검사를 생략하므로 전체 타입 검사 통과를 뜻하지 않는다.
- 회귀 테스트는 외부 생성기·DB·Adobe 렌더를 fixture로 대체한다. 별도 영상 추적 테스트와 FFmpeg 미디어 생성 검증도 포함하지만 실제 Windows AE 출력에 대한 시청 검수 완료는 아니다.
- 최종 렌더 자동 연결은 기존 Codex 검수·계속 진행 절차를 유지한다. `direction_pending`과 `review_pending`을 자동 승인하지 않는다.

## 후속 수정: 영상 좌표 지정 화면

영상 처리 워커만 연결해도 웹에서 좌표를 지정할 기준 화면이 없으면 준비를 완료할 수 없다. 기존 위치 지정 창은 `scene.image`가 없는 경우 요청 자체를 보내지 않고, 화면에는 “원본 이미지 불러오는 중…”을 계속 표시했다.

이를 다음과 같이 연결했다.

1. 영상만 있는 대사 씬을 열면 `prepare_video` 요청으로 저장된 원본 영상을 읽고 FFmpeg로 첫 프레임을 추출한다. 기준 이미지가 없는 사용자에게 이미지를 따로 올리도록 요구하지 않는다.
2. 추출한 PNG는 `speaker_video_reference`라는 별도 자료로 저장한다. 원본 영상이나 이미지 페이지의 이미지를 교체하지 않는다.
3. 프레임에 원본 영상 ID·경로·해시를 기록한다. 웹의 좌표 지정·자동 분석·수동 저장은 이 기준 프레임을 공유한다.
4. AE 제출 입력과 Python 입력 재검증도 같은 기준 프레임을 선택한다. 영상 파일 해시가 달라지면 추적 전에 검토 필요 상태로 전환한다.
5. 불러오기 실패·미디어 없음은 오류로 표시하고 다시 불러올 수 있다. 무한 로딩 문구를 유지하지 않는다. 새 안내는 태국어 모드에도 번역했다.

기준 프레임 준비는 얼굴·입의 자동 확정을 의미하지 않는다. 화면을 확인하여 직접 지정하거나 선택 씬 자동 분석을 실행한 뒤 저장해야 한다. 이후 다시 제출하면 새 영상 좌표를 포함한 작업 입력이 생성된다. 기존 확정 좌표가 있는 씬은 자동으로 다른 프레임으로 바꾸지 않는다.

후속 검증: 실제 FFmpeg 첫 프레임 추출 및 저장·재사용, 영상만 있는 씬의 API 준비→표시→좌표 저장, 에디터 요청 실행, 영상 교체 시 무효화, Python 기준 프레임 참조 및 영상 추적 경로를 테스트했다. Windows 실물 AE 렌더 검수와 운영 프로젝트의 좌표 확정은 별도다.
