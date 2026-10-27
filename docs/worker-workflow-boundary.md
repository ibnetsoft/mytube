# 대본워커와 통합워커의 역할

작업 소유권은 `std_projects.submitted_at`으로 나눈다. 유저웹의 화자 지정·이미지 영상화·최종 음성 확인을 마치고 제출하기 전에는 대본워커가 준비하며, 제출 후에는 통합워커가 실행한다.

| 단계 | 담당 | 작업과 설정 위치 |
|---|---|---|
| 제출 전 준비 | 대본워커 `http://127.0.0.1:3003` | `대본 설정`: 신규 대본 기본값, 언어·국가·스타일. `이미지·좌표·AE 연출 준비`: 원본, 얼굴·입 좌표, 검수한 입모양 소재, PSD·영역 레이어, 카메라·효과·전환 계획, 출력 방식·비율 |
| 사용자 확인 | 유저웹 | 이미지의 영상화·업로드, 최종 화자 지정, 음성·자막 확인과 제출. 화자가 바뀌어 준비 좌표와 일치하지 않으면 준비를 보완한 뒤 제출 |
| 제출 후 제작 | 통합워커 `http://127.0.0.1:3004` | `제출 후 실행·검수 상태`: 준비한 소재와 연출로 AE 실행, 최종 음성에 시간 맞춤, 실제 출력 검수, 최종 렌더. `영상 생성 모델 · API`: 제공자·모델·키 설정 |

AE는 통합워커의 실행 기능이다. AE를 위한 이미지 관찰·얼굴/입 좌표·입모양 소재·레이어·창작 연출 계획은 대본워커가 준비한다. 통합워커는 준비된 연출의 타이밍을 최종 음성에 맞추며 실행을 검증한다. `motion_automation_worker.py`의 `direction` 단계는 화면에서 **실행 검증·마무리 보정**으로 표시한다. `scene_direction_plan/v2`에서는 준비된 카메라·주요 연출을 유지하면서 마무리 효과 0~2개와 컷·크로스페이드를 보정할 수 있다. 구형 계약은 효과·전환까지 유지한다. 누락된 기본 소재·좌표는 대본워커에서 보완하고 다시 제출한다.

대본·씬의 창작 연출 의도는 `worker/codex_content_runner.py`, 실제 원본·PSD를 확인한 실행 계획은 `worker/ae_scene_preparation.py`와 `motion_preview_worker.py`의 direction 작업에서 준비한다. 실제 `AfterFX`·`aerender`는 통합워커가 있는 Windows 컴퓨터에서 실행한다. Vercel과 웹어드민은 AE 실행기가 아니다.

## 제작 상태와 웹어드민

`/admin/ae-worker`의 **After Effects 제작 현황**은 프로젝트별로 제출 전 연출·좌표·레이어 준비, 제출 후 입모양·모션·가로 웹툰·영역 AE 실행, 최종 조립을 함께 표시한다. 활성 작업은 페이지로 모두 수집하고, 이력은 준비·제작 큐와 최종 렌더 큐 각각 100건씩 페이지로 조회한다. 컴퓨터 온라인 여부·씬 제작 완료·검수 완료·최종 영상 완료는 구분한다. 관리자 게시·YouTube 업로드는 별도다.

실행 계열은 현재 유지한다. `motion_automation`은 연출 실행 검증·마무리 보정과 정책에 따른 출력 검수를 수행한다. `ae_mouth_job` 공통 파이프라인 v2는 제출 고정본을 기술적으로 조립하며 과거 자동 연출·미관 검수 단계를 모두 반복하지 않는다. 최종 조립은 `remote_render_queue`가 담당한다. 이번 현황 정리는 작업을 다시 제출하거나 큐를 자동 변환하지 않는다.

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

## 별도 제작 옵션 · 현재 비활성

2026-10-27부터 After Effects 씬 제작과 기본 FFmpeg 최종 조립을 사용한다. `auth-web/lib/productionEnginePolicy.json`의 `alternative_engines_enabled=false`가 공통 릴리스 정책이다. EffectCraft·FilmCraft·브라우저 Motion Studio는 접힌 별도 옵션으로 분리하며 선택·신규 제출·실행을 차단한다. FFmpeg는 기본 영상 조립 구성요소이므로 중지 대상이 아니다.

기존 대체 엔진의 설정·큐·결과는 보존하며 AE로 자동 변환하지 않는다. 미제출 프로젝트에서 After Effects와 기본 조립으로 전환·저장하고 필요하면 다시 제출한다. 통합워커는 비활성 대체 큐를 소비하지 않는다. 재활성화는 별도 릴리스로 웹·워커의 정책을 함께 검증해야 한다. 과거 통합 기록은 [EFFECTCRAFT_INTEGRATION.md](EFFECTCRAFT_INTEGRATION.md)를 참조한다.

일반 이미지·영상의 모션 제작도 `worker/ae_flat_scene.py`를 통해 실제 Adobe AE로 실행한다. 기존 MoviePy 프레임 제작 분기는 사용하지 않는다. 원본 단일 레이어와 저장된 카메라·효과만 전달하며, 영상은 1배속을 유지한다. 원본 영상이 확정 씬보다 짧으면 보완 상태로 중지한다. 최종 인코딩·조립은 FFmpeg가 담당한다. 이전 Python 모션 캐시는 새 AE 실행 결과로 간주하지 않으며, 사용자가 선택한 기존 소스 파일은 보존한다.


## 1~18씬 제출 영상 후작업 · 2026-10-27

`submitted_video_postwork/v1`은 사용자가 제출한 1~18씬 원본 영상에 적용한다. 일반 AE 설정이 꺼져 있어도 이 구간의 업로드 영상은 제출 시 `motion_automation` 공통 실행기로 등록한다. 프로젝트를 다시 제출하지 않는 기존 고정 작업은 자동 변경하지 않는다.

- 대본워커: 씬 대본의 정확한 문구를 근거로 `submitted_video_postwork` 효과·전환 지침을 작성한다. 반딧불은 해당 문구에 반딧불이 명시될 때만 요청한다. 밤이라는 이유만으로 넣지 않는다. 영상의 기존 카메라·몸동작은 유지한다.
- 유저웹: 원본 영상·대사 화자·확정 녹음·음향을 확인해 제출한다. 내레이션에는 입모양을 요청하지 않는다. 기존 19씬 이후 정지 이미지의 준비된 입모양 대상·소재는 유지한다.
- 통합워커: 실제 제출 영상의 화자를 로컬 Codex CLI로 확인하고 이동·크기·회전을 추적한다. **사용자가 명시적으로 요청한 제출 후 준비의 예외**로, 실제 기준 프레임에서 필요한 입 상태 패치만 준비하고 원본·닫힘·중간·열림 합성 검수를 통과시킨다. 다른 원화·동작·음성을 생성하는 권한은 아니다. 기존 정지 이미지 입모양은 사전 검수한 소재만 재사용한다.
- AE: 추적 입모양과 반딧불을 동일 원본 프리컴프에 한 번 합성한다. 추가 카메라·오디오 반응 조명은 넣지 않는다. 반딧불은 느리고 작은 광점으로 제한하고 화자 이동 범위와 자막·글자 영역을 피한다.
- 최종 조립: 이 제출 계약은 컷·짧은 암전 전환(`fade_black`)을 인접 씬 경계에서 한 번만 적용한다. 암전은 고정된 경계 전·후의 밝기만 조절하며 클립을 겹쳐 길이를 줄이지 않는다. 소스 핸들이 없는 크로스페이드를 정지·반복·시각 이동으로 흉내 내지 않는다. 영상 1배속과 확정 음성·자막 시간은 바꾸지 않는다. 영상이 짧으면 정지·반복·속도 변경으로 메우지 않고 보완 상태로 중지한다.
- 검수: 원본/출력의 같은 시각 프레임과 입 주변 확대, 정확한 대사 구간, 효과의 대본 근거와 위치, 전환·최종 음성 시간을 확인한다. 이 계약에는 검수 생략이나 필수 입모양의 원본 대체 정책을 적용할 수 없다. 실제 출력 검수 영수증이 없으면 최종 조립으로 넘어가지 않으며, 최종 경계·자막·음향 검수를 통과한 파일만 완료로 저장한다.

핵심 코드: `auth-web/lib/stdSubmittedVideoPostwork.ts`, `worker/submitted_video_postwork.py`, `worker/ae_flat_scene.py`, `worker/ae_scene_effects.py`. 이 구조는 실패한 작업의 원본·음성·완료 결과를 보존하며 재시도에서 지문이 일치하는 결과만 재사용한다.

이 계약의 DB 완료 함수는 실제 씬 검수·필수 입모양·최종 경계·음성 시간 영수증을 요구한다. 워커나 저장된 과거 정책에 검수 생략 값이 있어도 새 계약에는 적용하지 않는다. 마이그레이션 `submitted_video_postwork_review_gate`와 순수 JSON SQL 회귀 검증을 함께 관리한다.
