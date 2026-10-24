# Python 기본 최종 렌더 · FilmCraft 추가 옵션

FilmCraft는 기존 AIR 렌더워커와 별도로 설치하는 편집기 및 헤드리스 렌더러입니다.
씬 효과 엔진과 최종 합성기는 독립적입니다. AE 선택·기본값과 EffectCraft 선택을 유지합니다.
AE 또는 EffectCraft가 PSD 레이어·카메라·모션·효과를 제작하고, 최종 합성은 기본적으로 기존 Python/FFmpeg 경로를 사용합니다.
웹의 별도 **최종 렌더러** 메뉴에서 FilmCraft를 선택한 경우에만 `render_settings.motion.final_renderer: filmcraft`를 저장합니다. 이 선택은 효과 제작 엔진을 바꿔도 유지됩니다. 설정이 없으면 Python이 기본입니다.
FilmCraft 선택 패키지만 `final_renderer: filmcraft`와 검증 프로필을 고정하여 `services/filmcraft_final_service.py`로 전달합니다. Python 선택은 기존 합성 경로를 사용합니다. 이미 고정된 작업의 스냅샷은 수정하지 않습니다.
효과 완료 영상에는 카메라·효과를 재적용하지 않습니다. 최종 합성에서 AE/EffectCraft는 다시 실행하지 않습니다.
별도로 선택 가능한 FilmCraft 네이티브 씬 효과 옵션은 기존 `filmcraft_automation` 큐를 사용하지만, 이것은 최종 합성기 선택과 다른 설정입니다.
로컬 통합워커가 제출 후 씬 제작·확정 음성·자막·음향 합성·선택한 렌더러의 최종 출력을 진행하고, 실제 출력 검수를 통과해야 완료됩니다.

최종 합성은 이미지·영상 소스를 지원합니다. PSD 효과 제작은 그대로 AE/EffectCraft가 담당하고 그 출력 영상을 FilmCraft에 전달합니다. FilmCraft 네이티브 씬 효과 옵션 자체는 원본 PSD 리그를 직접 처리하지 않습니다.

## 별도 선택 가능한 FilmCraft 네이티브 씬 효과 모드

아래 원본 기반 카메라·벡터 연출 설명은 FilmCraft 자체로 씬 효과까지 만드는 추가 옵션에 해당합니다. AE/EffectCraft를 선택한 일반 흐름의 최종 합성은 검수된 효과 완료 씬 영상을 입력으로 사용합니다.
현재 경로는 `filmcraft-native-timeline-gpu-v3-balanced`입니다. 원본 이미지·영상과 확정 음성을 `.fcproj` 네이티브 타임라인에 직접 배치합니다.
카메라는 Motion/Opacity 키프레임, 연출 효과는 편집 가능한 벡터 레이어, 자막은 C1 캡션 트랙, 음향은 A1/A2/A3… 트랙으로 생성합니다.
최종 마스터도 원본 에셋에서 직접 합성합니다. 검수용 씬 MP4를 다시 이어 붙이거나 Python 프레임 캐시를 만들지 않습니다.
자막·BGM·겹치는 SFX·AI 삽입·디자인 PNG 오버레이도 FilmCraft 자체 합성/믹서에서 처리합니다. AE/EffectCraft 효과 제작은 유지하며, 최종 합성기는 Python 기본 또는 FilmCraft 추가 옵션으로 선택합니다.

로컬 `tools/filmcraft/gpu-receipt.patch`는 CLI 출력에 GPU 합성 프레임 수, CPU 대체 수, 선택된 GPU 장치 이름/종류를 추가합니다.
영상·효과 알고리즘을 바꾸는 패치가 아닙니다. 작업 시작 전 작은 GPU 합성을 실행하며, 하드웨어 GPU 확인에 실패하면 연출 분석/유료 AI 삽입 전에 멈춥니다.
최종 출력에서도 실제 GPU 합성 프레임 수가 0이거나 소프트웨어/알 수 없는 장치이면 성공 처리하지 않습니다.
프레임 전체가 CPU 합성으로 대체된 횟수도 기록합니다. 글꼴/벡터 래스터화 등 내부 전처리는 CPU에서 수행될 수 있으며, 이 카운터가 모든 처리의 GPU 전용 실행을 뜻하지는 않습니다. `GPU auto` 설정만으로 GPU 사용을 주장하지 않습니다.

제약: 원본 PSD 리그/브라우저 전용 경로·열 왜곡은 자동 변환하지 않습니다. 자막 폰트는 기존 웹 폰트 파일 또는 로컬 시스템에서 찾을 수 있어야 합니다.
네이티브 캡션의 하단 여백은 화면 높이의 0~45%, 배경만 별도로 이동하는 오프셋은 0이어야 합니다. 지원 범위를 벗어나면 명시적으로 오류를 반환합니다.
효과는 네이티브 벡터 표현으로 구현하므로 이전 Python/AE 출력과 픽셀 단위로 같다는 보장은 없으며, 기존 실제 출력 검수를 그대로 거칩니다.
네이티브 타임라인/연출 키프레임은 원본 미디어 참조와 함께 작업 폴더에 남아 편집기에서 열 수 있습니다.
기존 프레임 기반 캐시는 버전이 다르므로 재사용하지 않습니다. 새 검수 캐시는 네이티브 프로젝트/실행 기록/AI 원본 해시까지 일치해야 사용합니다.

이 경로를 사용하려면 아래 빌드가 설치된 컴퓨터에서 최신 `worker/local_media_supervisor.py`가 실행 중이어야 합니다.
상태 API·복구 명령·완료 RPC는 FilmCraft 전용 큐를 인식하며, 다른 엔진으로 자동 전환하지 않습니다.

별도 편집기와 CLI도 아래 명령으로 계속 사용할 수 있습니다.

## 빌드

```powershell
python scripts/build_filmcraft.py --jobs 2
```

`tools/filmcraft/source.json`의 고정 커밋에 관리되는 GPU 기록 패치만 적용하여 빌드합니다.
원본 커밋·패치 SHA-256·실행 파일 해시는 `build-manifest.json`에 기록합니다. 그 외 소스 변경이 있으면 빌드를 거부합니다.
Rust 1.95 이상과 해당 플랫폼의 네이티브 빌드 도구가 필요합니다.
이 컴퓨터의 기존 `.codex-temp/cargo`, `.codex-temp/rustup` 도구 체인도 사용합니다.
소스 기본 위치는 `.codex-temp/filmcraft-src`입니다. 기존 소스 위치는 `--source PATH`로 지정할 수 있습니다.
Windows 설치 패키지나 GitHub Release는 만들지 않습니다.

결과 위치: `output/filmcraft/windows-amd64/` (다른 OS에서는 플랫폼/아키텍처별 경로).

- `filmcraft.exe`: 독립 편집기
- `filmcraft-cli.exe`: 창 없이 실행하는 렌더 CLI 및 MCP 서버
- `build-manifest.json`: 소스 커밋, 버전, 실행 파일 SHA-256
- 원본 라이선스, NOTICE, 저작자 표시

## 실행

저장소 루트에서:

```powershell
python scripts/filmcraft.py editor
python scripts/filmcraft.py editor "C:\videos\project.fcproj"
python scripts/filmcraft.py inspect "C:\videos\project.fcproj"
python scripts/filmcraft.py render "C:\videos\project.fcproj" "C:\videos\filmcraft-result.mp4"
```

편집기에서 미디어를 가져와 타임라인을 편집하고 `.fcproj`로 저장합니다.
렌더 명령은 해당 프로젝트를 H.264/AAC MP4로 출력하고, 출력 옆에 `.filmcraft.json` 실행 기록을 남깁니다.
기록에는 소스 커밋, 프로젝트 및 출력 해시, 종료 코드와 CLI 진단이 포함됩니다.
이미 존재하는 출력/기록은 덮어쓰지 않습니다. 누락된 원본 미디어는 오류로 처리하며,
기존 엔진으로 자동 전환하거나 결과를 자동 승인하지 않습니다.

GPU 합성은 기본 `auto`이며 CLI가 장치 지원 여부를 판단합니다. CPU 합성은
`render ... --gpu-rendering off`로 명시할 수 있습니다.
빌드 해시를 확인한 뒤 실행하므로 바이너리를 직접 교체했다면 빌드 스크립트로 다시 설치해야 합니다.

AIR의 기존 `.aep`/`.ecproj` 및 제출 스냅샷을 `.fcproj`로 자동 변환하는 기능은 포함하지 않습니다.
원본 이미지·영상·확정 나레이션을 편집기에 가져와 별도 프로젝트로 작업할 수 있습니다.

원본: https://github.com/storytold/filmcraft
CLI 명령: https://github.com/storytold/filmcraft/blob/main/docs/agents.md

## 재검증

```powershell
python scripts/verify_filmcraft.py
```

생성한 320×180 이미지와 440Hz WAV를 네이티브 프로젝트에 배치하고 2초/24fps MP4를 출력합니다.
48개 프레임의 색상, 오디오 주파수, 기존 출력 보호, 원본 프로젝트 유지, 미디어 누락 오류를 확인합니다.
검증 자료와 JSON 결과는 설치 폴더의 `verification-*` 디렉터리에 남깁니다.
이 검증 스크립트는 PIL, NumPy, MoviePy를 사용합니다. 실제 FilmCraft 렌더러는 해당 라이브러리에 의존하지 않습니다.


## 네이티브 경로 검증

```powershell
python scripts/verify_filmcraft_native.py
```

생성한 원본 이미지/영상을 사용해 1080p 네이티브 마스터를 출력합니다. 카메라 이동·한/일 자막·전환·BGM 루프·겹치는 SFX·AI 삽입·디자인 오버레이를 실제 디코딩 결과로 확인합니다.
같은 타임라인의 GPU 출력과 CPU 참조 출력을 비교하고, 지원하는 12종 효과를 별도로 출력합니다.
검증용 Pillow/MoviePy/NumPy는 합성기의 의존성이 아니라 테스트 자료 생성/디코딩에만 사용합니다.
현재 작업에서는 웹/DB/서버 배포를 수행하지 않습니다. 웹 선택 메뉴 변경은 로컬 소스에 준비된 상태입니다.

자막은 선택한 시스템 글꼴의 문자 지원 여부도 검사합니다. 누락 문자는 사각형으로 출력하거나 임의 글꼴로 바꾸지 않고 작업을 중단합니다. 한/일 혼합 자막 검증에는 이 컴퓨터에 설치된 Noto Sans KR을 사용합니다.

## 기본 용량·화질·자막 프로필

`filmcraftNativeContract.json`의 `legacy-matched-1080p24-v1`을 최종 렌더 패키지에 고정합니다. 효과 워커 CLI의 기본 엔진은 AE이며 최종 합성기와 별개입니다.
1080p/24fps 기본은 네이티브 GPU 합성 + 하드웨어 H.264 Auto, VBR 목표 1540kbps/최대 2000kbps, AAC 192kbps/48kHz/모노입니다. 다른 해상도·FPS는 영상 비트레이트를 픽셀 수와 FPS에 비례해 조정합니다.
기존 렌더에서 사용한 정적 글꼴 파일을 전용 로컬 패밀리로 복제해 시스템 동명 가변 글꼴과 충돌하지 않도록 합니다. 글자 윤곽·굵기는 보존하고 ASS의 em 크기 및 하단 기준선에 맞춰 네이티브 캡션의 크기·여백을 계산합니다. 이 과정은 글꼴 메타데이터 변환이며, 자막 프레임을 미리 구워 넣는 과정이 아닙니다.
프로젝트 3376/37을 보정값 없이 기본 설정으로 출력했을 때 이전 보정 영상과 SHA-256까지 동일했습니다. 검증: `python scripts/verify_filmcraft_defaults.py`, 결과: `output/filmcraft/default-profile-verification/verification.json`.
기존 엔진·프로필로 고정된 제출을 임의로 새 프로필로 바꾸지 않습니다. 이전 FilmCraft 프로필은 현재 워커에서 재제출 안내로 중단하고, 새 제출부터 새 프로필을 적용합니다. 배포는 수행하지 않았습니다.

실제 AE 및 EffectCraft 완료 씬 각각의 FilmCraft 최종 합성 검증: `python scripts/verify_effects_then_filmcraft.py`. 결과는 `output/filmcraft/effects-then-final/verification.json`이며, 원본 효과 영상 해시 보존·효과 중복 적용 없음·240프레임 실제 GPU 합성·확정 음성 동기를 확인합니다.
