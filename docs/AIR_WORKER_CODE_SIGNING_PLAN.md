# AIR Worker — 코드 서명 계획 (AIR-0227E-P2 §16, AIR-0227E-P2-VALIDATION §13 재확인)

- 상태: **계획 문서만 — 실제 서명 여전히 미실시(서명 인증서 없음).** P2-VALIDATION에서 실제
  `AIRWorker.exe`/`AIRWorkerSetup-0.1.0.exe`를 빌드·설치까지 완료했지만, 둘 다 **미서명
  상태 그대로 배포 산출물이다** — production-ready로 표기하지 않는다.

## 0. P2-VALIDATION에서 다시 확인한 것

- `dist/onedir/AIRWorker/AIRWorker.exe`, `release/AIRWorkerSetup-0.1.0.exe` 둘 다 Authenticode
  서명 없음(`signtool verify` 실행 시 "서명되지 않음" 판정이 나올 것으로 예상 — 인증서가
  없어 signtool 자체를 실행할 수 없어 직접 실행하지는 않음).
- SmartScreen 검증도 인증서 없이는 의미 없음(신규 미서명 실행 파일은 SmartScreen 경고가
  뜨는 게 정상 동작).
- 서명 후 SHA256은 서명 전/후 값이 달라진다는 점만 이 문서에 미리 기록 — 실제 서명 시
  §12(버전 일치)의 SHA256 기록도 다시 갱신해야 함.

## 1. 무엇을 서명해야 하는가

- `dist/AIRWorker/AIRWorker.exe`(onedir 빌드 결과물, §P2-1)
- `release/AIRWorkerSetup-{version}.exe`(Inno Setup 인스톨러 산출물, `AIRWorker.iss`)
- (선택) onedir 폴더 내 다른 실행 파일이 있다면 함께 — 현재는 `AIRWorker.exe` 단일
  실행 파일만 존재.

## 2. 인증서 종류

- **표준 Authenticode 코드 서명 인증서** 또는 **EV(Extended Validation) 코드 서명 인증서**
  중 선택 필요 — CTO 결정 사항:
  - 표준: 저렴하지만 SmartScreen 평판이 다운로드 수 누적으로만 서서히 쌓임(신규
    배포 초기에는 "알 수 없는 게시자" 경고가 뜰 수 있음).
  - EV: 발급 시점부터 SmartScreen 평판 즉시 확보되지만, 더 비싸고 하드웨어 토큰
    (USB 토큰) 또는 클라우드 HSM(Azure Trusted Signing 등) 보관이 강제됨.
- AIR Studio Desktop이 이미 서명 중이라면 그 인증서를 재사용할지, AIR Worker 전용
  인증서를 별도로 둘지도 결정 필요 — 이번 지시사항의 "AIR Studio Desktop 채널과 혼합
  금지" 원칙을 엄격히 적용한다면 **별도 인증서 사용을 권고**(같은 조직이 발급받은
  인증서라도, 서명 파이프라인/CI 시크릿 자체는 AIR Worker 전용으로 분리).

## 3. 서명 시점(빌드 파이프라인 상)

```
PyInstaller onedir 빌드 (AIRWorker_onedir.spec)
        │
        ▼
① AIRWorker.exe 서명           <- signtool sign /fd sha256 /tr <timestamp-url> /td sha256 ...
        │
        ▼
Inno Setup으로 AIRWorkerSetup-{version}.exe 생성
        │
        ▼
② AIRWorkerSetup-{version}.exe 서명   <- 인스톨러 자체도 별도로 서명 필요(내부 exe가
                                          서명되어 있어도 인스톨러 껍데기는 서명 안 됨)
        │
        ▼
③ SHA256 sidecar 생성 + 배포
```

- **타임스탬프 서버 사용 필수**(`/tr https://timestamp.digicert.com` 류) — 서명 후
  인증서가 만료되어도 서명 시점이 유효했다는 것을 증명해 계속 신뢰되게 함.
- `_dev/build_worker.py`/`AIRWorker.iss` 빌드 이후 단계에 `signtool` 호출을 추가하는
  것을 후속 작업으로 제안(이번 PoC는 인증서 자체가 없어 미구현).

## 4. CI/시크릿 관리 (제안, 미구현)

- 서명 인증서(.pfx) 또는 HSM 접근 자격증명은 절대 저장소에 커밋하지 않는다 — CI
  시크릿(예: GitHub Actions secrets)으로만 보관, 빌드 시점에만 메모리에 로드.
- AIR-0225B에서 이미 확립한 "빌드 산출물에 자격증명이 섞여 들어가지 않게 하는" 원칙
  (`.env` 관련 사고 대응)과 동일한 경계선을 서명 인증서에도 적용 — 서명은 빌드 서버의
  격리된 단계에서만 실행하고, 개발자 로컬 머신에는 인증서를 두지 않는다.

## 5. 이번 PoC에서 실제로 한 것 / 안 한 것

- **한 것**: 서명이 필요한 산출물 목록화, 서명 시점/파이프라인 위치 설계, 인증서
  종류별 트레이드오프 정리.
- **안 한 것**: 실제 서명(인증서 없음), CI 파이프라인 구현, `signtool` 호출 스크립트
  작성 — 전부 CTO의 인증서 확보 결정 이후 착수 가능한 후속 작업.
