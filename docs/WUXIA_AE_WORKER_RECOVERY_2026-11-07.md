# 무협 AE 워커 소스 복구

1·2·3화 제출 입력은 실제 상태 원화와 말풍선·입모양 및 `wuxia_native_timeline/v3` 효과를 포함한다. 그러나 2026-11-07 현재 AE PC의 실제 1화 결과 26개는 `unchanged_source_passthrough/v1` PNG였다. 큐의 제작·검수 진행 표시는 무협 연출 실행의 증거가 아니었다. 이 출력은 완성 효과본으로 인정하지 않는다.

세 작업은 `awaiting_worker_update`, `enabled=false`로 보존했다. 원본·음성·동결 입력과 이전 출력 증거를 유지한다. 웹 배포와 AE PC의 Python 프로세스 갱신을 구분한다. 서버는 `required_worker_contract` 및 현재 점유 토큰에 묶인 지원 확인이 없는 구형 실행·완료를 거부한다. 구형 차단과 유효한 지원 확인을 실제 DB 트랜잭션으로 검사하고 롤백했다.

## AE PC에서 이어갈 순서

1. `python worker/local_media_supervisor.py --stop`으로 현재 작업 종료 후 새 점유를 멈춘다. `--status`에서 실제 중지를 확인한다. 다른 사용자 작업을 강제 종료하지 않는다.
2. `git status --short --branch`와 원격을 확인한다. 로컬 변경을 보존한 상태에서 `git fetch origin`, `git merge --ff-only origin/main`을 각각 실행한다. 충돌 시 자동 삭제·강제 초기화하지 않는다.
3. 기존 환경·자격 증명으로 감독 프로세스를 재시작해 최신 모듈을 읽게 한다. Windows 설치 프로그램이나 릴리스 태그는 만들지 않는다.
4. `python scripts/std_resume_wuxia_native.py`로 세 지정 작업의 소유권·상태·지원 계약을 검사한다. 실제 AE와 aerender가 있는 갱신 호스트에서만 `--enqueue`로 재개한다. 원화 그대로 넘긴 이전 결과는 증거로 보관하고 새 렌더 캐시로 쓰지 않는다.
5. 실제 결과의 `ambient_renderer`와 `adobe_flat_renderer`, 동결 계약 및 최종 MP4 SHA·길이·디코딩·효과 프레임을 확인한다. 등록 성공이나 JSX 준비만으로 실제 출력 완료를 보고하지 않는다.

작업 ID: 1화 `a05142f9-e6f6-4a94-b3c1-fd3188bd97e1`, 2화 `29ed803a-ffbd-4cfa-85ac-122bcba8f5e1`, 3화 `59cbfd69-526b-4613-86b0-7ea17be6b1df`.

로컬 근거는 `output/wuxia-effects-episodes01-03/AE_WORKER_VERSION_REPAIR.json`, `before-worker-version-hold-*.json`과 `QUALITY_NOTES.md`다. 실제 브라우저 재생 검사는 Chrome의 확장 UI 차단이 해제된 뒤 이어간다.

검증: 무협·워커 계약 Python 30개, 입모양 런타임·형상·준비 레이어 27개, 웹 회귀 33개가 통과했고 웹 프로덕션 빌드도 완료했다. 구형 일반 입모양 큐 테스트 3개는 변경 전 소스를 별도 프로세스에서 로드해도 동일하게 실패했다. 해당 테스트의 작업 fixture에 현재 필수 `pipeline_version=2`가 없어 점유 전에 거부되며 이번 무협의 선택 입모양 변경과 구분한다. 관련 원본 테스트는 임의로 고치지 않았다.
