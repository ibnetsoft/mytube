# AIR Worker — Third-Party Notices

AIR Worker (`AIRWorker.exe`)에는 다음 오픈소스 구성 요소가 포함되어 있습니다. 이 목록은
[AIR-0227E-P2] PoC 단계에서 확인된 주요 구성 요소를 기재한 것이며, 전체 의존성의
포괄적/최종 법적 감사는 아닙니다 — 상용 배포 전 CTO/법무의 정식 검토가 필요합니다
(`docs/AIR_WORKER_FFMPEG_LICENSE.md` 참고, 특히 FFmpeg는 별도 문서로 상세 기재).

## FFmpeg

- 라이선스: **GPL** (이 빌드는 `--enable-gpl`, `libx264`/`libx265` 포함)
- 출처: gyan.dev "essentials" 빌드, 버전 7.1
- 프로젝트: https://ffmpeg.org/
- 상세: `docs/AIR_WORKER_FFMPEG_LICENSE.md`

## imageio-ffmpeg (Python)

- 라이선스: BSD-2-Clause
- 프로젝트: https://github.com/imageio/imageio-ffmpeg
- 용도: 위 FFmpeg 바이너리를 패키지에 번들하고 경로를 찾아주는 래퍼

## MoviePy

- 라이선스: MIT License
- 프로젝트: https://github.com/Zulko/moviepy
- 용도: 슬라이드쇼/영상 합성 렌더 파이프라인

## FastAPI / Uvicorn

- 라이선스: MIT License (둘 다)
- 프로젝트: https://github.com/fastapi/fastapi, https://github.com/encode/uvicorn
- 용도: Local API(127.0.0.1 전용 관리 인터페이스)

## pywin32

- 라이선스: PSF License(Python Software Foundation 유사 permissive 라이선스)
- 프로젝트: https://github.com/mhammond/pywin32
- 용도: Windows DPAPI 토큰 암호화(`win32crypt`), 프로세스 트리 종료 보조

## Pillow (PIL)

- 라이선스: HPND (permissive, BSD 유사)
- 프로젝트: https://python-pillow.org/
- 용도: 이미지 처리(슬라이드쇼 렌더 파이프라인 경유)

---

이 파일은 설치 디렉터리에 함께 배포되어야 합니다(`[Files]`에 포함 권장, 이번 PoC에서는
문서만 작성 — 설치 스크립트에 실제로 포함시키는 것은 후속 작업).
