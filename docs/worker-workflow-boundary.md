# 대본워커와 통합워커의 역할

작업 소유권은 `std_projects.submitted_at`으로 나눈다. 유저웹의 화자 지정·이미지 영상화·최종 음성 확인을 마치고 제출하기 전에는 대본워커가 준비하며, 제출 후에는 통합워커가 실행한다.

| 단계 | 담당 | 작업과 설정 위치 |
|---|---|---|
| 제출 전 준비 | 대본워커 `http://127.0.0.1:3003` | `대본 설정`: 신규 대본 기본값, 언어·국가·스타일. `이미지·좌표·AE 연출 준비`: 원본, 얼굴·입 좌표, 검수한 입모양 소재, PSD·영역 레이어, 카메라·효과·전환 계획, 출력 방식·비율 |
| 사용자 확인 | 유저웹 | 이미지의 영상화·업로드, 최종 화자 지정, 음성·자막 확인과 제출. 화자가 바뀌어 준비 좌표와 일치하지 않으면 준비를 보완한 뒤 제출 |
| 제출 후 제작 | 통합워커 `http://127.0.0.1:3004` | `제출 후 실행·검수 상태`: 준비한 소재와 연출로 AE 실행, 최종 음성에 시간 맞춤, 실제 출력 검수, 최종 렌더. `영상 생성 모델 · API`: 제공자·모델·키 설정 |

AE는 통합워커의 실행 기능이다. AE를 위한 이미지 관찰·얼굴/입 좌표·입모양 소재·레이어·창작 연출 계획은 대본워커가 준비한다. 통합워커는 준비된 연출의 타이밍을 최종 음성에 맞추며, 누락된 소재나 좌표를 임의로 새로 생성하지 않는다. 필요한 준비가 없으면 수정 필요 상태로 남긴다.

## 코드와 저장소

- `worker/workflow_roles.py`: 제출 상태와 자산 종류에 따른 공통 소유권, DB 조회 필터와 실행 직전 검증.
- `worker/script_preparation.py`: 대본워커의 단일 CLI 실행 풀에 준비 작업을 직렬 등록. `ae_scene_preparation`, `ae_speaker_coordinates`, `region_layer_package`, `motion_preview(input.task=direction)` 담당.
- `worker/local_media_supervisor.py`: 제출된 `ae_mouth_job`(공통 파이프라인 v2), `motion_automation`, `region_motion_plan`, 영상 미리보기와 최종 렌더만 실행.
- `remote_drive_worker.py`: 렌더 후보 조회·점유·실행에서 유저웹 제출 상태를 재검증.
- `worker/codex_local_console.py`, `worker/script_preparation_api.py`: 3003의 준비 UI와 인증된 로컬 API.
- `worker/local_production_ui/source.tsx`: 두 워커 내부에 직접 표시하는 공통 UI. `data-worker-stage`에 따라 준비 편집과 제출 후 상태/모델 설정을 분리.
- `scripts/local_worker_settings.cjs`: `worker_role`별 읽기·쓰기 허용 목록. 통합워커의 준비 설정 저장과 대본워커의 모델/API 설정 차단.
- `auth-web/lib/stdWorkflowBoundary.ts`, `stdSubmissionPipeline.ts`, `stdMotionAutomation.ts`: 진행 중 준비와 화자 좌표를 확인하고 제출 패키지를 고정. PSD는 준비·검수된 패키지만 사용.
- 대본 기본값은 `global_settings`의 `codex_script_defaults_<WORKER_ID>`, 프로젝트 연출은 `std_projects.project_payload.render_settings`, 준비 결과·작업 이력은 `std_project_assets`, 제출 고정본은 `std_pipeline_runs`에 저장한다. 모델/API 키는 기존 서버 암호화 저장소를 사용한다.

## 종료한 중복 경로

- 음성 저장만으로 제출 전 AE 미리보기를 생성하던 `ensureSyncedMouthPreview`는 작업을 등록하지 않는다. `prepare_preview` 요청은 410을 반환한다.
- 이미지 공개 시 `prepared_mouth_preview.prepare_preview`는 준비 영수증만 기록한다. AE나 인코더를 시작하지 않는다.
- 대본워커의 하이라이트 실행·검수 API와 메뉴를 종료했다. `/api/ae-highlight*`는 410이다.
- 대본 승인 후 별도 음성·영상 큐를 시작하던 `sermon_queue`를 종료했다. 기존 결과 파일은 유지하고 이후 제작은 유저웹 제출의 공통 파이프라인을 사용한다.
- 통합워커의 토픽/하이라이트 자동 발견과 제출 후 PSD·좌표·레이어 재생성을 종료했다. 기존 `preview_sync` AE 작업은 통합워커가 가져오지 않는다.
- 논버벌도 유저웹에서 만든/업로드한 영상을 제출할 수 있다. 제출 전 영역 AE 렌더를 제출 조건으로 요구하지 않는다. 영역 AE 실행에는 사전 검수한 레이어가 필요하다.

다시 준비해야 할 경우 제출을 취소하거나 프로젝트를 재개한 뒤 대본워커에서 수정하고 유저웹에서 다시 확인·제출한다. 관리자 게시와 YouTube 업로드는 별도 절차다.
