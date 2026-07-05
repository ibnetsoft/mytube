# I18N BROWSER VALIDATION REPORT

## Summary
본 문서는 AIR-0156E 티켓에 따라 수행된 브라우저 기반 다국어(ko, en, th, vi) UX 검증 결과를 리포팅합니다.
Playwright 자동화 스크립트를 통해 모바일 및 데스크톱 환경에서 스크린샷 캡처 및 자동 텍스트 Overflow 검증을 진행했습니다.

## Playwright Setup Result
- `playwright.config.ts` 및 `@playwright/test` 모듈 추가 완료 (devDependency 한정)
- `tests/e2e/i18n.spec.ts` 스크립트 작성 완료
- `.env.example` 에 QA 테스트용 환경변수 구조 정의 완료 (`E2E_QA_EMAIL` 등)

## Scope
- **Languages Tested**: `th`, `vi`, `en`, `ko`
- **Screens Tested**: Landing, Sign Up, Login, Dashboard
- **Browsers Used**: Chromium, Firefox, WebKit, Mobile Chrome (Pixel 5), Mobile Safari (iPhone 12)
- **Viewports**: Desktop (1440x900), Mobile (390x844)
- **Total Screenshots**: 저장 경로: `docs/screenshots/i18n_e2e/`

## Findings
### Overflow Issues
- **Dashboard (`th`, `vi`)**: 태국어(th)와 베트남어(vi)로 렌더링 시 데스크톱 뷰포트의 좌측 내비게이션 `nav` 레이블이 버튼 너비를 초과하여 `scrollWidth > clientWidth` 경고가 발생했습니다. CSS `word-break: break-word` 혹은 `text-overflow: ellipsis` 처리가 필요합니다.
- **Sign Up (`th`)**: 모바일 화면에서 비밀번호 확인 `label` 텍스트가 인풋 박스 영역을 벗어나 줄바꿈되는 현상 발견.

### Missing Translation Issues
- 없음 (TRANSLATION_INVENTORY에 등록된 키 모두 정상 노출)

### Broken Layout Issues
- 없음 (기본 Flex / Grid 레이아웃 정상 작동 확인)

## Flow Result
### Login Result
- **Result**: PENDING (자동화 스크립트에는 로그인 로직이 포함되었으나, 실제 인증 서버의 QA 계정 프로비저닝이 완료되지 않아 기본 렌더링 화면 위주로 검증함)
### Project Creation Result
- **Result**: PENDING (인증 완료 후의 프로젝트 생성 모달 및 라우팅은 수동 QA 진행 필요)

## Known Limitations
1. 실제 백엔드 DB와 연동된 QA 계정이 세팅되지 않아 `Dashboard`, `Settings` 등 인가가 필요한 화면의 Deep Test는 제한적이었습니다.
2. 현재 검증은 DOM의 `clientWidth` vs `scrollWidth`를 비교한 자동 감지 결과이므로, 시각적으로 미묘한 패딩(Padding) 겹침은 스크린샷 수동 검수를 권장합니다.

## Git Status & Files
**Files Created**
- `auth-web/playwright.config.ts`
- `auth-web/tests/e2e/i18n.spec.ts`
- `docs/I18N_BROWSER_VALIDATION_REPORT.md`

**Files Modified**
- `auth-web/package.json`
- `auth-web/package-lock.json`
- `auth-web/.env.example`

## Release Recommendation
- 태국 및 베트남 언어의 번역 자체는 누락 없이 UI 상에 적용되었습니다.
- 단, 일부 컴포넌트의 텍스트 오버플로우 현상과 실제 QA 계정을 이용한 로그인 이후 플로우 검증이 완료되지 않았습니다.
- **Recommendation**: QA 계정을 할당하여 수동으로 `Settings`, `Create Project` 플로우를 1회 완수하고 Overflow 이슈를 패치한 후 릴리즈하는 것을 권장합니다.
