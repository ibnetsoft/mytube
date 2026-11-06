# GIF 보조 움직임과 편집 시간 연동

PNG와 기존 상태 컷을 보존하면서 승인한 영역만 움직이는 선택 기능이다. GIF를 HTML 이미지로 자동 재생하지 않는다. 별도 생성 도구로 만든 GIF를 로컬에서 투명 PNG 패치로 준비하고 AIR Studio와 통합워커가 같은 밀리초 시계를 사용한다.

## 실제 실행 경로

- AIR Studio `/std`의 `playbackTime` → `wuxiaSceneFrame` → `ambientFrameIndex` → 체크섬 확인한 PNG 패치 → 기존 말풍선·타이포.
- 제출 → `registerMotionAutomation`의 동결 입력 `scenes[].ambient_loops` → `motion_automation_worker.render_base` → 상태별 원화·실제 GCS 프레임 다운로드/검증 → `ae_flat_scene.write_jsx` → 원화 source comp에 HOLD 프레임 레이어 → 기존 AE 효과와 글자 → 최종 조립.
- 보조 움직임이 있으면 원화 passthrough 및 일반 슬라이드 제출로 생략하지 않는다. 작업 취소·소유권 확인은 기존 워커의 `fresh()`를 각 다운로드에도 적용한다. 기존 결과는 입력 fingerprint와 ambient renderer 계약이 맞을 때만 재사용한다.
- 기존 회차에 새 움직임을 자동으로 덧붙이지 않는다. 실제 사용할 원화와 움직임 범위·보호 좌표를 먼저 확인한다.

## 준비

현재 지원하는 제작 경로는 기본 AE + 16:9 정지 PNG 원화다. 상태별 원화 SHA와 해당 루프의 원화 SHA가 같아야 한다. 여러 상태 원화는 편집 미리보기와 같은 최종 음성 시계로 상태 컷·말풍선·타이포까지 동결한다. 해당 상태가 표시될 때만 그 상태의 패치를 덧붙인다. 다른 상태 원화에 속한 움직임을 선택 원화 위에 덮지 않는다. PSD·업로드 영상·가로 패널·EffectCraft·FilmCraft 장면에 이 계약을 자동 변환하지 않는다.

```sh
.venv-script/bin/python scripts/prepare_ambient_loop.py \
  --source /absolute/state.png --gif /absolute/stars.gif \
  --output /absolute/prepared-stars --role background \
  --region '[0.02,0.02,0.25,0.20]' \
  --protected-regions '[[0.40,0.20,0.65,0.70]]' \
  --start-ms 0 --end-ms 12000 --phase-ms 0
```

좌표는 원화 기준 정규화 `[left, top, right, bottom]`이다. 보호 좌표에는 실제 얼굴·머리와 글자·꼬리·중요 정보의 전체 범위를 넣는다. 인물 없는 배경만 `[]`를 허용한다. 영역은 원화 면적의 35% 이하이며 보호 좌표와 겹칠 수 없다. 이 검사는 얼굴을 자동 인식하거나 움직임의 미술적 품질을 판정하지 않는다. 승인 좌표의 실제 이미지 검수는 별도로 필요하다.

GIF는 원화와 같은 캔버스, 2~16프레임, 프레임별 20~2000ms 지속시간이어야 한다. Pillow가 disposal을 해석한 뒤 영역 밖 픽셀은 모두 투명하게 제거한다. 영역 안의 얼굴·소품 변형은 좌표 검수에서 배제해야 한다. GIF에 들어 있던 글자는 사용하지 않고 별도 그래픽을 유지한다.

기본 명령은 로컬 `manifest.local.json`, poster와 PNG 프레임만 만든다. `--upload-prefix std-ambient/<unique-package>`를 추가하면 설정된 로컬 워커 GCS 자격으로 원본 PNG/GIF, poster, 프레임과 게시 manifest를 올린다. 모델 API 호출은 없다. 필요하면 `--package /absolute/episode.json --scene E04S001 --state <asset_id>`로 **로컬 패키지 JSON**의 정확한 상태에 `ambient_loops`를 붙인다. 유저웹에는 기존 회차 패키지 등록 절차로 해당 패키지를 등록하고 readback한다. 이 명령 자체가 유저웹 DB를 변경하지는 않는다.

## 타이밍

상태의 `ambient_loops` 배열에 게시 manifest를 넣는다. `enabled:false`는 끄기, `repeat:false`는 한 번 재생 후 마지막 패치 유지다. `start_ms <= 씬 로컬 시간 < end_ms`에서만 보인다. `phase_ms`는 루프 내 시작 위상이며 컷마다 다시 시작하려면 해당 컷 시작 시각을 `start_ms`로 정한다. 전역 타임라인을 탐색해도 결과가 달라지지 않는다. 다른 상태로 전환하면 패치를 표시하지 않는다.

프레임 구간은 반개구간이다. 지속시간 `[100,200,50]`이면 로컬 시간 `[0,100)`에 0번, `[100,300)`에 1번, `[300,350)`에 2번이다. AE는 24/30fps 각 출력 프레임의 시간을 같은 방식으로 선택한다. 출력 FPS보다 짧은 구간은 샘플되지 않을 수 있으며 프레임 보간·크로스페이드는 하지 않는다. 영상 자체의 재생 속도·반복 정책을 완화하지 않는다.

## 검증 기록 (2026-11-07)

- 실제 GIF disposal 디코딩·지속시간 보존, 보호 영역/영역 밖 알파 배제, 원화·프레임 변조 거부를 Python 테스트로 확인했다.
- JS/Python의 가변 프레임 길이·정확한 경계·위상·반복/1회 재생과 출력 프레임 시간의 결과가 같다.
- 실제 프리뷰 컴포넌트를 브라우저 fixture에서 확인했다. 씬 시작 10초 기준 10.20초는 1번, 10.40초는 2번, 정지 후 2번 유지, 다음 상태 11.10초는 패치 0개, 역방향 10.20초 탐색은 다시 1번이었다. 원본 PNG와 고정 얼굴이 유지됐다. 이는 운영 회차의 미술 검수가 아닌 기능 검증이다.
- AE JSX에 실제 프레임 파일과 HOLD 키가 들어가는 것을 확인했다. 이 컴퓨터에는 After Effects/aerender가 없어 실제 AE 렌더 영상 검증은 수행하지 않았다. 이 기록을 최종 AE 출력 검증으로 대신하지 않는다.
