# AIR Worker — Google Drive 입출력 어댑터 (AIR-0227C Stage 8)

- 상태: **구현 완료 / 실 Drive 계정·폴더 기준 미검증 (테스트 자격증명 없음)**
- 구현: `worker/drive_adapter.py`, `worker/upload_adapter.py::GoogleDriveUploadAdapter`

## 1. 기존 구조 분석 (Stage 1/AIR-0227B에서 이미 확인한 내용 재확인)

`services/google_drive_service.py`의 `download_file`/`upsert_file`은 **사용자별 OAuth
token_path**를 요구한다 - AIR-0225B의 service_role(전역 관리자 키)과는 성격이 다른, 훨씬
좁은 범위의 자격증명이다. 기존 `remote_drive_worker.py`(살아있는 Drive-릴레이 기능)가
이미 같은 모듈을 같은 방식으로 쓰고 있어, 새 인증 체계를 만들지 않고 그대로 재사용했다.

## 2. 설계

```
AIRWORKER_DRIVE_TOKEN_PATH  - 기존 OAuth 토큰 파일 경로 (CTO/ops가 사전 발급)
AIRWORKER_DRIVE_FOLDER_ID   - 격리된 작업 폴더 ID (Drive 루트 절대 아님)
```

- **다운로드**(`download_input_package`): file_id로 메타데이터를 먼저 조회해 `parents`에
  설정된 `AIRWORKER_DRIVE_FOLDER_ID`가 포함되어 있는지 확인 - **Drive 전역의 임의 file_id를
  받아들이지 않고, 지정 폴더 안의 파일만 허용**(요구사항 "전체 Drive 접근 대신 지정 폴더
  접근"). 크기(1바이트~500MB) + 확장자(.zip만) 검증 후 다운로드, 다운로드 후 실제 파일
  크기도 재검증(부분 다운로드 방지).
- **파일명**: Drive에서 받은 `name` 메타데이터를 `_safe_basename()`으로 정제(디렉터리
  구분자·상대경로 시퀀스 제거) - Drive 메타데이터는 (계정이 탈취되면) 공격자 영향권에 들
  수 있는 값이라 로컬 경로 조합에 그대로 쓰지 않는다(path traversal 방어).
- **업로드**(`upload_output`): 파일명은 워커가 직접 `{job_id}.mp4` 형태로 생성(Drive
  메타데이터에 의존하지 않음), 확장자(.mp4)와 로컬 파일 존재/비어있지 않음을 업로드 전에
  검증, 지정 폴더로만 업로드.
- **재시도**: 3회, 지수 백오프(2s/4s/6s) - `central_client.py`와 별개의 단순한 재시도
  (Drive API 자체 라이브러리가 이미 어느 정도 재시도를 내장하고 있어 과도하게 공격적인
  백오프는 두지 않음).
- **로그**: 자격증명(token_path 파일 내용, 액세스 토큰)은 어디에도 로깅하지 않는다.
  예외 메시지도 `type(exc).__name__`만 남기고 원문 메시지는 생략 - Drive API 예외가 요청
  URL을 포함하는 경우가 있어(토큰 자체는 헤더에 있으므로 URL엔 없지만) 보수적으로 접근.

## 3. GoogleDriveUploadAdapter 연결

`worker/upload_adapter.py::GoogleDriveUploadAdapter.upload()`가
`drive_adapter.upload_output()`을 호출하도록 실제로 연결했다(AIR-0227B에서는
`NotImplementedError`였음). `LocalCopyUploadAdapter`가 여전히 로컬 E2E 픽스처가 실제로
쓰는 어댑터이고, `render_worker.py`도 아직 `LocalCopyUploadAdapter`를 하드코딩해서 쓴다 -
`GoogleDriveUploadAdapter`로 전환하려면 `AIRWORKER_DRIVE_*` 환경변수 설정 + 어댑터 선택
로직 추가가 필요하며, 이건 실 Drive 자격증명이 없는 이번 세션에서는 의도적으로 보류했다.

## 4. 왜 실측하지 않았는가, 그리고 다음에 뭐가 필요한가

이 환경에는 격리된 테스트용 Google Drive 계정/폴더/OAuth 토큰이 없다. "테스트용 계정 또는
격리 폴더만 사용한다. 실제 운영 콘텐츠 폴더는 CTO 승인 없이 사용하지 않는다"는 지시를
문자 그대로 지키려면, 그런 테스트 자산이 실제로 준비되어야 한다 - 코드만으로 만들어낼 수
없는 부분이다.

**다음 세션에서 실측하려면 CTO/ops가 준비해야 할 것**:
1. 테스트 전용(또는 최소 권한) Google 계정으로 이미 인증된 `token.json` 1개
2. 그 계정 소유이거나 공유받은 격리 폴더 1개, folder_id 확보
3. `AIRWORKER_DRIVE_TOKEN_PATH`/`AIRWORKER_DRIVE_FOLDER_ID` 환경변수로 위 값 주입
4. 그 폴더에 테스트용 .zip 자산 하나 업로드 → `download_input_package(file_id, ...)` →
   `render_pipeline_adapter.prepare_temp_dir` 호출까지 이어붙이는 통합 테스트 1건 추가
5. 렌더 완료 후 `upload_output`으로 같은 폴더에 업로드되는지, 다른 폴더 파일은 안 건드는지
   폴더 스코프 확인

## 5. 보안 체크리스트 (요구사항 대비)

| 요구사항 | 상태 |
|---|---|
| 자격증명 로그 미노출 | ✅ 코드 리뷰로 확인 (token_path 값도 로그하지 않음) |
| Worker 전용 최소 권한 계정 | 설계상 지원(어떤 token_path를 넣든 동작) - 실제 최소권한 계정 발급은 CTO/ops 몫 |
| 전체 Drive 대신 지정 폴더 | ✅ `parents` 검증으로 강제 |
| 자격증명 파일 커밋 금지 | ✅ 환경변수로만 전달, 저장소에 아무 것도 커밋하지 않음 |
| 파일명/경로 traversal 방어 | ✅ `_safe_basename()` |
| 파일 크기/확장자 검증 | ✅ 다운로드(.zip, ≤500MB)/업로드(.mp4) 양쪽 |
