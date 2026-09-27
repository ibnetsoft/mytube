# Adobe 로컬 준비 상태 점검 — 2026-09-26

2026-09-27 추가 확인: AE의 레이어 PSD 스모크 7종과 강조 문구 변형 1종이
실제 `AfterFX`/`aerender`에서 4초 MP4로 출력됐고 계획·렌더 QA를 통과했다.
아래 최초 점검 시점의 미완성 목록은 이 검증 이전 기록이다. 현재 만화 연출
검수 절차는 `MANGA_SCENE_QA.md`를 따른다.

## 후속 구현 결과

- Premiere가 가져올 수 있는 FCP7 XML로 교체하고 음성 트랙을 추가했다.
- 미디어를 포함한 ZIP과 압축 해제 후 경로를 고치는 `relink.py`를 추가했다. 작업 폴더도 즉시 삭제하지 않는다.
- 음성 GCS 파일이 있으면 동일 미디어로 FFmpeg 최종 MP4를 만들고 업로드한 뒤에만 `ready`로 기록한다. 자막은 선택 가능한 MP4 트랙이다.
- AE 기본 해상도를 1920×1080으로 맞추고 실제 PSD 자산이 제공되면 레이어 합성으로 가져온다.
- FFmpeg 1초 샘플 MP4 생성과 관련 자동 테스트 26개는 통과했다. 실제 AE 렌더와 Premiere/AME 자동 내보내기는 아직 검증되지 않았다.

아래 항목은 최초 점검 당시의 기록이며, 현재 구현 상태는 이 후속 결과와 `ADOBE_GPU_RENDER_HOST.md`를 기준으로 한다.

## 동기화

- 로컬 main 및 origin/main: `6c267337e7ef93ad7d373f5a5f2ec4a000929978`.
- 최신 7개 커밋 반영: AE 모션, 이야기 검수, CS6 호환, 전 씬 AE 후처리, 하이브리드 PSD, Adobe GPU 호스트.
- 기존 미커밋 토픽 등록 기능 및 comic 실험은 stash로 보관 후 복원. index.html 충돌은 AE 메뉴와 웹 토픽 승인 스크립트를 모두 보존하여 해결. 백업 stash 유지.
- Adobe/대본/토픽/저장소 관련 테스트 54개 통과. 테스트는 실제 Adobe 렌더 성공을 의미하지 않는다.

## 설치 및 실행

- After Effects 2026: 26.5. `AfterFX.exe`, `AfterFX.com`, `aerender.exe` 감지.
- `aerender -help`: 26.5x89 명령행 응답 확인.
- Premiere Pro 2026: 26.5.1, 실제 홈 화면까지 시작 확인.
- Media Encoder 2026: 실행 파일 감지. 실제 인코딩 미검증.
- GPU: NVIDIA GeForce RTX 5060, 드라이버 32.0.16.1062. Adobe GPU 가속 사용 여부/성능은 미검증.
- AE: 현재 worker의 `_write_jsx`로 3초 검기 효과 테스트 JSX 생성 후 .com/.exe 실행 시도. 충돌 복구 옵션 창 확인. 점검 중 프로세스가 종료되었으며 AEP/AVI/MP4는 생성되지 않았다. 종료 원인은 확정하지 않았다.
- 테스트 파일: `%LOCALAPPDATA%/Temp/air-adobe-check-20260926/smoke.jsx`. 운영 큐 렌더·DB 변경·미디어 업로드는 실행하지 않았다.

## 설계 대비 미완성/불일치

1. **Premiere 출력 브리지 미구현**: `premiere_final_worker.py`는 `package_ready`까지만 기록한다. JSX는 타임라인 import만 시도하며 SRT 적용, 음성/BGM/SFX 배치, MP4 출력, 최종 결과 업로드를 실행하지 않는다. `ADOBE_GPU_RENDER_HOST.md`에도 브리지 구현이 후속 단계임을 명시한다.
2. **타임라인 형식 불일치**: `_write_fcpxml`은 FCP X `.fcpxml` 1.8을 생성한다. Adobe 공식 문서상 Premiere는 이 형식을 직접 import할 수 없다. FCP7 호환 XML 또는 실제 UXP 시퀀스 생성 경로가 필요하다.
3. **PSD 계획과 실행 미연결**: 대본 단계에는 PSD 레이어 계획이 있지만 AE 워커는 현재 PNG/JPEG 정지 이미지를 가져온다. 생성된 레이어 패키지를 씬별 AE 합성으로 연결하는 경로는 확인되지 않았다.
4. **출력 기본값 차이**: AE 기본 720×720, Premiere 기본 1920×1080. 운영 16:9 씬에 사용할 해상도와 효과 좌표를 맞춰 검증해야 한다.
5. **실행 시점 차이**: GPU 호스트 문서는 제출 후 Adobe 처리라고 설명하지만 AE worker는 ready 상태의 `topics_queue`를 조회한다. 제출/승인 조건으로 필터링하지 않는다.
6. **패키지 이동성**: Premiere XML은 로컬 미디어 경로를 가리키는데 기본 처리 후 작업 폴더를 삭제한다. manifest의 GCS 참조로 미디어를 복원하고 경로를 다시 연결하는 브리지가 필요하다.

## 결론

Adobe 설치/탐지 및 Premiere 시작은 확인했지만 현재 코드로 완전 자동 제작이 준비됐다고 판단할 수 없다. AE 시작/스크립트 실행 → 짧은 실제 렌더 성공을 먼저 확보하고, Premiere import 형식과 최종 출력 브리지, PSD 및 미디어 연결을 완성해야 한다.

공식 참고: https://helpx.adobe.com/premiere/desktop/organize-media/import-files/migrate-from-final-cut-pro-x.html
# 2026-09-26 후속 검증

`premiere_final_worker`의 기본 출력을 Adobe Media Encoder 앱 자동 내보내기로 연결했다.
워커가 48 kHz 스테레오 AAC 중간 영상을 만들고, AME 시작 스크립트로 H.264
프리셋을 적용한 뒤 완료 이벤트와 출력 파일을 확인한다. 실제 로컬 샘플 MP4 두 건
(내레이션 포함, 무음 오디오)을 앱에서 출력했고 자막 결합도 확인했다. 사용자가
이미 실행한 AME 세션은 건드리지 않고 작업을 중단한다. 아래의 기존 미완료
목록은 이 변경 전 감사 기록이다. AE 실제 렌더와 운영 GCS 업로드는 이번
검증에 포함되지 않았다.
