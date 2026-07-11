# AIR-0225B — 영향받은 릴리즈 자산 인벤토리 (자산 삭제 전 기록)

## 삭제 사유
`SUPABASE_SERVICE_ROLE_KEY`가 평문 포함된 `app/.env`가 아래 릴리즈의 ZIP/설치파일 안에
들어있었음 (근거: `worknote/AIR-0225B-stage0-service-role-removal-investigation.md` §5).

## 삭제 시각
`2026-07-11` (이 문서 기록 직후 실행)

## 영향 범위
- 저장소: `ibnetsoft/AIR-releases` (Public)
- 태그: `v2.0.8` ~ `v2.3.5` (19개 릴리즈)
- 미영향(정상): `v0.1.1`~`v0.1.5`, `v2.0.0`~`v2.0.7` — 코드 이전(`3fee1e13`, 2026-07-09 22:12 KST) 이전 빌드라 자산 삭제 대상 아님. 그대로 유지.

## 삭제 전 자산 목록 (release_id | 자산명 목록)

| 태그 | GitHub Release ID | 자산 (6개씩) |
|---|---|---|
| v2.3.5 | 352525132 | AIRStudio-2.3.5-win-x64.zip, .zip.sha256, AIRStudioSetup-2.3.5.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.3.4 | 352511783 | AIRStudio-2.3.4-win-x64.zip, .zip.sha256, AIRStudioSetup-2.3.4.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.3.3 | 352502067 | AIRStudio-2.3.3-win-x64.zip, .zip.sha256, AIRStudioSetup-2.3.3.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.3.2 | 352492349 | AIRStudio-2.3.2-win-x64.zip, .zip.sha256, AIRStudioSetup-2.3.2.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.3.1 | 352437913 | AIRStudio-2.3.1-win-x64.zip, .zip.sha256, AIRStudioSetup-2.3.1.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.3.0 | 352431301 | AIRStudio-2.3.0-win-x64.zip, .zip.sha256, AIRStudioSetup-2.3.0.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.9 | 352425049 | AIRStudio-2.2.9-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.9.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.8 | 352415127 | AIRStudio-2.2.8-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.8.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.7 | 352137545 | AIRStudio-2.2.7-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.7.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.6 | 352102417 | AIRStudio-2.2.6-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.6.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.5 | 351921921 | AIRStudio-2.2.5-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.5.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.4 | 351916719 | AIRStudio-2.2.4-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.4.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.3 | 351907442 | AIRStudio-2.2.3-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.3.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.2 | 351887934 | AIRStudio-2.2.2-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.2.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.1 | 351884253 | AIRStudio-2.2.1-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.1.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.2.0 | 351869819 | AIRStudio-2.2.0-win-x64.zip, .zip.sha256, AIRStudioSetup-2.2.0.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.1.0 | 351853389 | AIRStudio-2.1.0-win-x64.zip, .zip.sha256, AIRStudioSetup-2.1.0.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.0.9 | 351580562 | AIRStudio-2.0.9-win-x64.zip, .zip.sha256, AIRStudioSetup-2.0.9.exe, .exe.sha256, latest.json, latest.json.sha256 |
| v2.0.8 | 351544397 | AIRStudio-2.0.8-win-x64.zip, .zip.sha256, AIRStudioSetup-2.0.8.exe, .exe.sha256, latest.json, latest.json.sha256 |

**합계: 19개 릴리즈 × 6개 자산 = 114개 자산**

## 조치
- 위 114개 자산 전부 삭제 (릴리즈 자체/태그/노트는 유지 — 이력 보존).
- `latest.json`도 함께 삭제 대상에 포함: 매니페스트 자체에는 키가 없지만, 삭제하지 않고 두면
  구버전 앱들이 "업데이트 가능"으로 인식한 뒤 삭제된 zip/exe로 다운로드를 시도해 404가 나는
  상태가 되므로, 매니페스트까지 함께 제거해 "현재 안전한 업데이트 없음"을 명확히 한다.
- 다운로드 카운트(삭제 전 확인, 실사용 노출 규모 참고용): v2.0.8 설치파일 10회, v2.2.0 zip 1회,
  그 외 대부분 0회 — 조사 과정에서 제가 v2.3.5 zip을 검증 목적으로 1회 내려받고 즉시 삭제한 것
  포함.
