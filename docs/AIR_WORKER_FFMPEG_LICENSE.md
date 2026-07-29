# AIR Worker — 번들 FFmpeg 출처/라이선스 (AIR-0227E-P2)

- 상태: **사실관계 문서화 완료 / 법적 적합성 최종 확정은 CTO·법무 소관 (이 문서가 임의로
  "배포 가능"이라고 결론 내리지 않음 — 지시사항의 명시적 금지 사항)**

## 1. 출처/버전

`AIRWorker.exe`(onefile)와 `AIRWorker/`(onedir) 둘 다 Python 패키지 `imageio-ffmpeg`
0.6.0(BSD-2-Clause, `imageio_ffmpeg` 자체 라이선스는 문제 없음 — 아래는 그 패키지가
번들해서 배포하는 **ffmpeg 실행 파일 자체**에 대한 문서)이 자동으로 내려받아 패키지에
포함해 둔 바이너리를 그대로 사용한다. PyInstaller 빌드 시 `_pyinstaller_hooks_contrib`의
표준 훅(`hook-imageio_ffmpeg.py`)이 이 바이너리를 자동으로 datas에 포함시킨다(수동 다운로드
아님, 코드 한 줄도 우리가 작성하지 않음).

이 개발 머신에 설치된 실제 바이너리로 확인한 버전 배너:
```
ffmpeg version 7.1-essentials_build-www.gyan.dev
Copyright (c) 2000-2024 the FFmpeg developers
built with gcc 14.2.0 (Rev1, Built by MSYS2 project)
```
- 출처: gyan.dev의 "essentials" 빌드(Windows용 커뮤니티 정적 빌드 배포처, ffmpeg 공식
  다운로드 페이지에 안내된 제3자 빌드 중 하나)
- 빌드 옵션(배너에서 확인): `--enable-gpl --enable-version3 --enable-libx264
  --enable-libx265 --enable-libvpx --enable-libaom --enable-libopenjpeg
  --enable-libwebp --enable-libass --enable-libfreetype --enable-libmp3lame
  --enable-libopus --enable-libvorbis` 외 다수(전체 목록은 `ffmpeg -version` 출력 참고)

## 2. 라이선스 판정 — **GPL 빌드** (LGPL-only 아님)

`--enable-gpl`이 켜져 있고 `libx264`/`libx265`(둘 다 GPL) 같은 GPL 코덱이 함께 링크되어
있으므로, 이 특정 바이너리는 전체적으로 **GPL(v2/v3 계열)** 라이선스가 적용된다. `imageio_ffmpeg`
패키지가 기본으로 받아오는 빌드가 GPL인 것이지, LGPL-only(코덱 제한판) 빌드가 아니다.

## 3. 미확정 사항 (CTO/법무 결정 필요, 이 문서가 임의로 결론짓지 않음)

- **재배포 방식**: AIR Worker는 이 ffmpeg 바이너리를 **서브프로세스로만 호출**하고
  코드를 링크/수정하지 않는다 — 실무에서 흔히 "별도 프로그램 호출"로 취급되어 호출하는
  쪽 소프트웨어까지 GPL 전파를 강제하지 않는다고 보는 경우가 많으나, 이는 법적으로
  확정된 결론이 아니라 통상적 실무 관행이다.
- **GPL 준수 의무**: GPL 빌드를 상용 제품에 재배포할 경우 통상 (a) 해당 바이너리의
  소스 코드 제공(또는 서면 제공 의사 표시), (b) 라이선스 고지문 동봉, (c) 저작권
  표시 유지가 요구된다 — AIR Worker가 이걸 다 하고 있는지는 이번 PoC 범위에서
  구현하지 않았고, §THIRD_PARTY_NOTICES(아래)에 기본 고지만 넣어뒀다.
- **대안**: LGPL-only 빌드(코덱 제한판, 예: libx264/libx265 제외)로 교체하면 GPL 의무를
  회피할 수 있으나, 그러면 render 파이프라인이 요구하는 `libx264` 인코더를 못 쓰게 되어
  현재 렌더 파이프라인과 호환 안 됨 — 이 트레이드오프는 CTO 결정 사항.

## 4. ffprobe — 이번 PoC에서 **미포함**

`imageio-ffmpeg`는 `ffmpeg` 실행 파일만 번들하고 `ffprobe`는 포함하지 않는다. 이 개발
환경에는 별도 경로(제3자 앱 "Vrew"의 설치 폴더)에 ffprobe.exe가 존재하는 것을 확인했으나,
**그 바이너리는 다른 회사의 제품에 번들된 것으로 라이선스/재배포 조건을 확인할 수 없어
그대로 복사해 우리 제품에 넣지 않았다.** 이번 세션은 네트워크 다운로드가 불가능한 샌드박스
환경이라 신뢰할 수 있는 출처(gyan.dev, BtbN 등 ffmpeg 공식 안내 배포처)에서 별도로
ffprobe.exe를 내려받아 포함하는 작업도 하지 못했다 — **P2-7(ffprobe 사이드카 포함)은
미완료로 명시.** 후속 작업 시 실제 인터넷 접근이 있는 빌드 머신에서 ffmpeg와 동일 버전대의
ffprobe.exe를 받아 `packaging/windows/AIRWorker.spec`/`AIRWorker_onedir.spec`의 `binaries`에
직접 추가하는 것을 권고(별도 사이드카 폴더로, `imageio_ffmpeg`가 관리하는 ffmpeg 경로와
헷갈리지 않게).
