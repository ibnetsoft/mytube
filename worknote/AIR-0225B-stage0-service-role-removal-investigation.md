# AIR-0225B — Stage 0: 데스크톱 앱 service_role 키 노출 조사 보고서

## Task ID
`AIR-0225B` (선행 문서: [`AIR-0225-service-role-key-migration-plan.md`](./AIR-0225-service-role-key-migration-plan.md))

## Date
`2026-07-11`

##상태
**조사 완료. 코드/설정 변경 없음. 키 값은 이 문서 어디에도 기록하지 않음.**
(변경 실행은 CTO 승인 후 별도 단계에서 진행)

---

## 🔴 최우선 긴급 사항 (BLOCKER #0 — 이 문서에서 가장 먼저 볼 것)

**`ibnetsoft/AIR-releases`는 Public 저장소입니다 (`gh repo view` 확인: `"isPrivate":false`).**
`v2.0.8`부터 오늘 배포한 `v2.3.5`까지, 현재 그 저장소에 공개적으로 걸려있는 **약 18개 릴리즈의
ZIP/설치파일 안에 `SUPABASE_SERVICE_ROLE_KEY`가 평문으로 포함되어 있고, 로그인 없이 누구나
다운로드 가능**합니다 (아래 §5에서 실제 아카이브 목록으로 검증, 값은 출력하지 않음).

이건 "배포 전에 고쳐야 할 설계 문제"가 아니라 **이미 발생한 노출 사고**입니다. 현재 GitHub Secrets에
등록된 `SUPABASE_SERVICE_ROLE_KEY` 값은 "이미 공개된 값"으로 취급해야 합니다. 코드 이전 작업
(Stage 0의 나머지 항목, 25개 이상 파일)은 시간이 걸리지만, **키 폐기·재발급 자체는 별도로 지금
바로 처리할 수 있는 조치**이고 코드 이전 완료를 기다릴 이유가 없습니다.

지시사항에 따라 **키 폐기/재발급을 제가 직접 실행하지는 않았습니다.** 이 판단과 실행 타이밍은
CTO 결정 사항으로 아래 "CTO 추가 결정 필요사항" §1에 올립니다. 다만 사실관계 확인을 위해
`gh api`로 각 릴리즈 자산의 다운로드 횟수만 조회했습니다 (값 조회 아님) — 실사용 다운로드는
현재 낮습니다(예: v2.0.8 설치파일 10회, v2.2.0 zip 1회, 최신 v2.3.5는 0회 — 이 보고서 작성 중
제가 검증 목적으로 1회 내려받고 즉시 삭제한 것 포함해 실질적으로 거의 없음). **다만 Public
저장소라 다운로드 카운터에 잡히지 않는 경로(직접 링크, 크롤러, 캐시 등)로 이미 유출되었을
가능성을 배제할 수 없으므로, 카운터가 낮다는 것이 "안전하다"는 근거는 아닙니다.**

---

## 1. service_role이 workflow에서 주입되는 정확한 흐름

```
GitHub Secrets (repo: ibnetsoft/mytube, private)
  └─ SUPABASE_SERVICE_ROLE_KEY
       │
       ▼  .github/workflows/windows-release.yml:117
          ("Build Windows package" 스텝의 env: 블록)
       $env:SUPABASE_SERVICE_ROLE_KEY  (러너 프로세스 환경변수)
       │
       ▼  tools/build_windows.ps1:184
       $EnvSupabaseKey = $env:SUPABASE_SERVICE_ROLE_KEY
       │
       ▼  build_windows.ps1:186-188
          (if ($EnvSupabaseUrl -and $EnvSupabaseKey) 가드)
       $EnvLines += "SUPABASE_SERVICE_ROLE_KEY=$EnvSupabaseKey"
       │
       ▼  build_windows.ps1:214
       release/staging/AIRStudio/app/.env   ← 평문 파일 생성
       │
       ├──▶ build_windows.ps1:258 (Compress-Archive $StagingRoot/*)
       │    AIRStudio-{version}-win-x64.zip  →  app/.env 포함 (§2, §5 검증됨)
       │
       └──▶ packaging/windows/AIRStudio.iss:28
            (Source "...\staging\AIRStudio\*" DestDir "{app}" recursesubdirs)
            AIRStudioSetup-{version}.exe  →  설치 시 이용자 PC에 app/.env로 복사
```

### 별도의 2차 경로 (CI에서는 현재 발동 안 하지만 구조적으로 존재)

`packaging/windows/AIRStudio.spec:29-37`에 **PyInstaller 자체의 `datas` 목록에도**
`(".env", ".")` 항목이 있습니다 (`if os.path.exists(path)`로 조건부). 이건 저장소 루트에
`.env` 파일이 있으면 그걸 그대로 `dist/AIRStudio/.env`로 넣는 로직으로, `build_windows.ps1`의
스테이징 단계보다 **먼저** 실행됩니다.

- CI(GitHub Actions)에서는: 매번 새로 체크아웃하고 `.env`는 git에 커밋된 적이 없으므로
  (`.gitignore:3`에 `.env` 등록, `git ls-files`로 추적 안 됨 확인) 이 조건이 항상 거짓 →
  **CI 공식 릴리즈에서는 이 경로가 실질적으로 no-op임을 확인.**
- 로컬 빌드에서는: 이 저장소가 있는 개발 머신에 지금 실제로 저장소 루트 `.env` 파일이
  존재합니다(오늘 날짜, 934바이트 — 파일 존재 여부만 확인했고 내용은 열지 않았습니다). 만약
  누군가 CI를 거치지 않고 `pyinstaller` 또는 `build_windows.ps1`을 로컬에서 직접 돌리면,
  **이 로컬 `.env`가 그대로 배포 산출물에 들어갈 수 있는 독립적인 2번째 경로**입니다.
  Stage 0 수정 시 `build_windows.ps1`의 스테이징 write뿐 아니라 **이 spec 파일의 `.env` datas
  항목도 함께 제거하거나, 최소한 service_role이 아닌 값만 허용하도록 손대야 완전히 막힙니다.**

---

## 2. 최종 exe/zip에 포함되는 경로

| 산출물 | 내부 경로 |
|---|---|
| `AIRStudio-{version}-win-x64.zip` | `app/.env` (zip 루트의 `app/` 폴더 아래) |
| `AIRStudioSetup-{version}.exe` 설치 후 | `%LOCALAPPDATA%\AIRStudio\app\.env` (`AIRStudio.iss:11` `DefaultDirName={localappdata}\AIRStudio`) |

두 산출물 모두 같은 `release/staging/AIRStudio/app/.env` 스테이징 파일에서 나옵니다 — 즉
하나를 고치면 둘 다 고쳐집니다 (원인이 하나라는 뜻이지, 검증은 각각 따로 해야 함 — §9 참고).

---

## 3. 로컬 앱(데스크톱)에서 service_role을 사용하는 파일과 기능

`config.py`에 중앙 정의가 **없고**, 아래 9개 파일이 각자 `os.getenv("SUPABASE_SERVICE_ROLE_KEY")`를
독립적으로 호출합니다 — 한 곳만 고쳐서 끝나는 구조가 아닙니다.

| 파일:행 | 변수명 |
|---|---|
| `services/web_admin_client.py:88` (property `supabase_key`) | 중심 클라이언트 |
| `app/routers/auth.py:80` (`_supabase_headers()`) | 자체 헤더 구성 |
| `app/routers/settings.py:553` | 자체 헤더 구성 |
| `app/routers/user_topics.py:43` (`_supabase_headers()`) | 자체 헤더 구성, `web_admin_client` 안 거침 |
| `services/dispatcher_service.py:86` | 자체 헤더 구성 |
| `services/remote_drive_render_service.py:46` | 자체 헤더 구성 |
| `services/render_queue_worker.py:40` | 자체 헤더 구성 |
| `remote_drive_worker.py:80` (별도 PyInstaller 타겟, `PicadiriRemoteWorker.spec`) | 필수값 — 없으면 `RuntimeError` |

`services/web_admin_client.py`는 클라이언트 하나뿐이고 **anon/service_role 구분이 아예 없습니다.**
`desktop_login()`(383행)과 `desktop_change_password()`(401행) 2개 메서드만 auth-web
(`/api/desktop-login`, `/api/desktop-change-password`)으로 이미 이전되어 이 키를 안 씁니다.
그 외 이 파일의 나머지 약 35개 메서드(`fetch_profiles`, `resolve_user_id`, `sync_wallet_info`,
`submit_withdrawal_request`, `delete_auth_user`, `update_tenant_commission` 등)와, 이 클라이언트를
우회해서 직접 헤더를 구성하는 위 6개 파일 전부가 여전히 이 키로 동작합니다.

**중요 정정**: 워크플로 파일의 코드 주석은 "데스크톱 로그인 자체는 더 이상 이 키가 필요 없다"고
써있지만, 실제로는 `POST /api/auth/login` 핸들러가 비밀번호 검증(`desktop_login`, 프록시됨) 직후
같은 요청 안에서 `auth_service.login_user()`를 호출하고, 이 함수가 내부적으로
`fetch_profile_by_email`(회원 등급/토큰 잔액 표시), `fetch_global_api_keys`(공용 AI 키 로드),
`update_preferred_language` 등 **service_role을 쓰는 호출을 최소 3곳 더** 실행합니다. 즉 **로그인
플로우 전체는 아직 이 키에서 자유롭지 않습니다** — "로그인만 이전 완료"라는 기존 코멘트는
좁은 의미(비밀번호 검증 그 자체)로만 참입니다.

anon key(`NEXT_PUBLIC_SUPABASE_ANON_KEY` 등)에 해당하는 경로는 Python 코드 전체에 **전혀
존재하지 않습니다** (grep 0건). 현재 데스크톱 앱은 "service_role 아니면 접근 불가" 구조입니다.

---

## 4. 제거 시 영향받는 기존 기능 / auth-web·JWT·RLS 대체 방안

기존 `AIR-0225` 문서의 우선순위 표를 그대로 채택하되, 이번 조사에서 추가로 확인된 항목
(로그인 잔여 호출, 죽은 코드)을 반영해 갱신합니다.

| 영역 | 대표 파일 | 영향받는 기능 | 대체 방안 |
|---|---|---|---|
| 로그인 잔여 호출 | `services/auth_service.py:282,290`, `app/routers/auth.py:407` | 로그인 시 등급/토큰잔액 표시, 공용 AI키 로드, 언어 동기화 | `desktop_login`과 같은 패턴으로 `auth-web/app/api/desktop-login`이 이 정보까지 한 번에 응답하도록 확장 (신규 라운드트립 최소화) |
| 회원가입/비밀번호 | `app/routers/auth.py` (register, forgot/reset password, 이메일 인증) | 가입, 비밀번호 재설정, 이메일 인증코드 | `auth-web/app/api/desktop/*` 신규 라우트, `desktop_login` 패턴 재사용 (AIR-0225 §3 그대로) |
| **출금 신청/이력** | `app/routers/settings.py` (`/api/withdrawal/request`, 중복 라우트 포함) | USDT 출금 신청·조회 — 금전 이동 | auth-web 프록시로 전환 (최우선, 금전 민감) |
| **토큰 차감** | `app/routers/video.py:1126-1143` | 렌더링 시 payout/토큰 동기화 | auth-web 프록시 또는 서버 측 원자적 차감 API |
| 테넌트/커미션 관리자 | `app/routers/admin_tenant.py` | 화이트라벨 테넌트 관리, 커미션율 변경 | auth-web 관리자 API로 이전 (관리자 전용이라 상대적으로 긴급도 낮음) |
| 프로젝트 동기화 | `services/project_sync_service.py` | 기기 간 프로젝트 메타데이터 동기화 | auth-web 프록시 (읽기 위주 — anon key + RLS로도 가능한지 검토 가치 있음) |
| 추천인 대시보드(데스크톱 내) | `app/routers/referral.py`, `app/routers/admin_referrals.py` | 추천인 트리/커미션/출금 (데스크톱 내 UI) | **auth-web에 AIR-0223으로 이미 구축된 동일 기능과 중복** — 이전보다 **데스크톱 라우터 자체 폐기**를 우선 검토 (AIR-0225 §4 순서6과 동일 결론 재확인) |
| 학습자료 동기화 | `services/learning_sync_service.py` | NotebookLM 자료 동기화 | auth-web 프록시 |
| 자동 게시 | `services/auto_publish_service.py` | 예약 자동 업로드 스케줄러 | auth-web 프록시 또는 서버 측 스케줄러로 완전 이관 검토 |
| TTS 음성 관리 | `app/routers/admin_voices.py`, `app/routers/tts.py:392` | 커스텀 보이스 CRUD/목록 | auth-web 프록시 |
| 에셋 매칭 | `app/routers/asset_matching_api.py`, `app/services/asset_matching_service.py` | 기기 간 씬-에셋 자동/수동 매칭 | auth-web 프록시 |
| 음악 템플릿 | `app/routers/music.py:212` | 음악 기획 템플릿 목록 | anon key + RLS로 대체 가능성 높음(읽기 전용 공개 데이터일 가능성) — 검토 필요 |
| QA 임계값 | `services/qa_service.py:73` | LUFS/블랙프레임 등 전역 QA 설정값 조회 | anon key + RLS 또는 정적 설정 파일로 전환 검토 (민감정보 아님) |
| 원격 렌더 큐 | `services/remote_drive_render_service.py`, `services/render_queue_worker.py` | 렌더 대상 "Google Drive API" 선택 시 작업을 `remote_render_queue`에 등록/상태 동기화 | **[확인 완료]** `main.py:645,1573`, `app/routers/video.py:1147,1969,2330,2371`, `app/routers/music.py:15,539`에서 직접 호출됨 — `services/`가 `AIRStudio.spec`의 `collect_submodules("services")`로 메인 앱에 통째로 포함되고, 실제로 사용자가 "Google Drive API" 렌더를 선택할 때마다 이 서비스 안에서 서비스롤로 Supabase에 작업 행을 기록/갱신함. **메인 AIRStudio.exe 코드 경로가 맞으므로 제거 대상에 포함.** auth-web 프록시로 전환 필요 |
| (별도 계열, 제거 범위 밖) 원격 GPU 워커 실행파일 | `remote_drive_worker.py`, 루트 `PicadiriRemoteWorker.spec`, `_dev/build_remote_worker.py` | "옆 PC"에서 운영자가 직접 실행하는 별도의 GPU 렌더 워커(`PicadiriRemoteWorker.exe`) — `docs/REMOTE_DRIVE_WORKER.md`에 문서화됨 | **[확인 완료]** `windows-release.yml`/`build_windows.ps1`/`AIRStudio.spec` 어디에도 참조되지 않는 완전히 별도의 빌드 산출물(`dist\PicadiriRemoteWorker.exe`), 자체 `.env.remote-worker.example`으로 별도 배포. **일반 고객에게 배포되는 AIRStudio 패키지에는 포함되지 않음** — 이번 Stage 0(공개 배포물) 범위 밖. 다만 이 워커도 service_role을 자체 `.env`로 갖고 있으므로, 운영자가 이 실행파일과 `.env`를 신뢰할 수 없는 PC(외주/파트너 렌더팜 등)에 배포하지 않도록 별도 하드닝 과제로 트래킹 권장(AIR-0225 계열 후속 이슈로 분리) |
| 주제 큐 | `app/routers/user_topics.py` | 추천 주제 피드, 주제 클레임(작업 배정) | auth-web 프록시로 전환, `web_admin_client` 우회하고 raw `requests` 쓰는 부분부터 정리 |
| **죽은 코드(사전 존재, 이번에 발견)** | `app/routers/settings.py:1239,1248,1284,1293`(중복 정산 라우트), `app/routers/referral.py:107`, `app/services/referral_engagement_service.py:41,47` | 존재하지 않는 `web_admin_client.is_admin_user()`/`get_settlement_summary()`/`call_rpc()`/`rpc()` 호출 — 호출되면 즉시 `AttributeError` | 이번 이전 작업과 무관한 **기존 버그**. 이전 대상에서 제외하되, 어차피 손대는 파일이니 같은 PR에서 정리하거나 최소한 이슈로 기록 |

---

## 5. 과거 release artifact 노출 가능성 (실측)

- **커밋 시점**: `3fee1e13 "feat: embed Supabase credentials in CI-built packaged app"`,
  `2026-07-09 22:12:40 +0900`.
- **GitHub Actions 실행 로그로 검증(마커 문자열만 확인, 키 값은 절대 조회 안 함)**:
  - 커밋 이전 실행(예: run `28999093379`, v2.0.2 빌드, 06:35 UTC 트리거) → 로그에 `.env` 기록
    관련 메시지 자체가 없음 → **이 키가 없던 스크립트 버전**.
  - 커밋 이후 첫 실행(run `29020601503`, v2.0.8 빌드, 13:13 UTC 트리거, 커밋 시각 13:12 UTC
    바로 다음) → 로그에 `"Writing packaged .env with Supabase credentials..."` 확인 →
    **이 빌드부터 키가 포함됨**.
- **실제 아카이브로 재검증**: `gh release download v2.3.5 --repo ibnetsoft/AIR-releases`로
  최신 zip을 내려받아 `unzip -l`(목록만, 압축 해제 안 함)로 확인한 결과 `app/.env` 280바이트
  존재 확인. 확인 직후 로컬 사본 즉시 삭제, 내용은 전혀 열람하지 않음.
- **결론**: **`v2.0.8`부터 오늘 `v2.3.5`까지 (현재 `gh release list`에 보이는 26개 중 약 18개,
  전부 지금도 공개 다운로드 가능)에 키가 포함되어 있습니다.** `v0.1.1`~`v0.1.5`, `v2.0.0`~`v2.0.7`은
  이 코드 이전이라 포함 안 됨.
- 저장소 자체(`ibnetsoft/AIR-releases`) Public 여부는 최상단 BLOCKER #0 참고.
- GitHub Actions **워크플로 런 아티팩트**(`windows-release.yml` "Upload release artifacts to
  workflow run" 스텝, 30일 보관)에도 동일한 zip/exe가 별도로 올라갑니다. 이건 `ibnetsoft/mytube`
  (Private 확인됨) 리포에 접근 권한이 있는 사람만 볼 수 있어 Public 노출보다는 범위가 좁지만,
  **키 폐기 시 이 30일 보관분도 함께 무의미해지므로 별도 삭제 조치는 필요 없음** (키 자체가
  무효화되면 이 안의 사본도 자동으로 안전).
- 로그 자체에 키 값이 출력된 흔적은 없음(스크립트 전체를 grep해도 `.env` 내용을 echo/cat/type
  하는 코드가 없고, `Write-Host`는 항상 "N개 줄을 썼다"는 카운트만 출력). GitHub Actions의
  시크릿 자동 마스킹도 안전망으로 작동하나, 이번 건은 애초에 값을 출력한 적이 없어 마스킹
  여부와 무관하게 안전했습니다 — **문제는 로그가 아니라 최종 산출물 파일 자체입니다.**

---

## 6. 키 교체가 필요한 환경 목록

값은 기록하지 않고, "이 환경에 이 키가 설정되어 있으므로 교체 시 갱신이 필요하다"는 위치만
나열합니다.

| 환경 | 위치 | 비고 |
|---|---|---|
| GitHub Actions Secrets | `ibnetsoft/mytube` 저장소 Secrets → `SUPABASE_SERVICE_ROLE_KEY` | Windows 릴리즈 빌드가 여기서 읽음 (§1) |
| Vercel 프로젝트 환경변수 | `mytube` 프로젝트(auth-web) → Development / Preview / Production 각각 | 사용자가 스크린샷으로 직접 확인시켜준 화면. auth-web의 정상 동작에 필요 — **회전 시 3개 환경 전부 갱신 필요, 서버 재배포 필요** |
| 로컬 개발 환경 | 이 저장소 루트 `.env` (git 미추적, 현재 파일 존재 확인) | 개발자 각자 로컬 `.env` — 회전 후 각자 갱신 필요, 회전 사실을 팀에 공지해야 로컬 개발이 갑자기 인증 실패로 막히지 않음 |
| (확인 필요) 다른 배포 환경 | `services/remote_drive_render_service.py`/`render_queue_worker.py`/`remote_drive_worker.py`가 참조하는 원격 렌더 워커 서버 | 이 워커가 실제로 어디서 도는지(사용자 PC vs 자체 서버) 확인 안 됨 — CTO 결정 §4 |

---

## 7. GitHub Secrets 목록 (이름만, 값 없음)

`gh secret list --repo ibnetsoft/mytube` 결과 (이름·최종수정일만):

| 이름 | 최종 수정 |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | 2026-07-09 |
| `RELEASES_REPO_TOKEN` | 2026-07-08 |
| `SMTP_FROM` | 2026-07-10 |
| `SMTP_HOST` | 2026-07-10 |
| `SMTP_PASS` | 2026-07-10 |
| `SMTP_PORT` | 2026-07-10 |
| `SMTP_USER` | 2026-07-10 |
| `SUPABASE_SERVICE_ROLE_KEY` | 2026-07-11 |

(`NEXT_PUBLIC_SUPABASE_URL`은 비밀값이 아니라 공개 URL이라 위험도가 다름 — 참고로 같이 기록. `SUPABASE_SERVICE_ROLE_KEY`가 오늘(2026-07-11) 수정된 이력이 있는데, 이 세션에서 제가 값을 바꾼 적은 없으므로 다른 경로로 이미 갱신되었을 가능성이 있음 — 사실관계만 보고, 원인은 CTO 확인 필요.)

---

## 8. 안전한 수정 순서 (제안)

### Phase 0 — 지금 바로 가능 (코드 이전과 독립적, CTO 승인 시 즉시 실행 가능)
1. Supabase 대시보드에서 `service_role` 키 재발급(기존 값 즉시 무효화).
2. §6의 3개 환경(GitHub Secrets, Vercel 3개 환경, 팀 로컬 `.env`)에 새 값 반영.
3. 재발급 즉시 **과거에 배포된 모든 public 아티팷트 속 구 키는 자동으로 무력화**됨 — 코드
   이전 완료를 기다릴 필요 없이 이 시점에 노출 위험 자체는 해소됨.
4. auth-web이 새 키로 정상 재기동하는지 확인(재배포 필요할 수 있음, Vercel 환경변수 변경은
   보통 재배포 필요).

### Phase 1 — 기능 이전 (AIR-0225 우선순위 유지, 이번 조사로 갱신)
1. 로그인 잔여 호출 3곳 (§4 표 1행) — 이미 만든 `desktop-login` 패턴 확장이라 비용 최소.
2. 회원가입/비밀번호 재설정.
3. 출금 신청/이력 (금전 최우선).
4. 토큰 차감(video.py).
5. 관리자 전용(admin_tenant.py) — 노출 빈도 낮아 우선순위 낮춤 가능.
6. 나머지 조회/동기화 일괄(project sync, learning sync, TTS 음성, 에셋 매칭, 음악 템플릿, QA
   설정) — 대부분 읽기 위주라 일부는 anon key+RLS로 대체 가능성 검토.
7. `admin_referrals.py`(데스크톱 내 추천인 관리) 폐기 여부 결정 — 중복 기능이라 이전보다 삭제가
   더 맞을 수 있음.
8. 원격 렌더 워커 3파일 — §CTO 결정 §4 확인 후 (사용자 PC 배포물이 아니면 이번 범위 제외 가능).

### Phase 2 — 배포 파이프라인에서 키 완전 제거
1. `tools/build_windows.ps1`의 `.env` 작성 로직에서 `SUPABASE_SERVICE_ROLE_KEY` 라인 제거.
2. `.github/workflows/windows-release.yml`의 `env:` 블록에서 해당 시크릿 참조 제거.
3. `packaging/windows/AIRStudio.spec`의 `(".env", ".")` datas 항목도 제거하거나, 남기더라도
   service_role이 없는 `.env`만 허용하도록 확실히 정리(로컬 빌드 2차 경로 차단, §1 참고).
4. 데스크톱은 이 시점부터 anon key(있다면)+사용자 JWT만으로 동작.

### Phase 3 — 검증
1. 저장소 루트에 `.env`가 전혀 없는 클린 체크아웃으로 로컬 빌드 1회 수행 → 정상 부팅 확인.
2. §9의 아티팩트 문자열 검사 수행, service_role 패턴 0건 확인.
3. §10 회귀 테스트 전체 통과.
4. 신규 버전 배포, 릴리즈 노트에는 "보안 개선"만 언급하고 키/경로 세부사항은 기록하지 않음.

---

## 9. release artifact 문자열 검사 방법 (제안, 아직 구현 안 함)

Supabase `service_role` 키는 JWT 형식(`eyJ...` 로 시작하는 점 3개짜리 base64url 문자열, payload에
`"role":"service_role"` 포함)입니다. 이 구조적 특징을 이용해 **값을 몰라도** 탐지 가능한
정규식 기반 스캐너를 CI의 "Publish GitHub Release" 스텝 **직전**에 게이트로 추가하는 것을 제안합니다.

1. 빌드 산출물(zip 압축 해제 디렉토리, exe 3종 원본 바이너리 모두)을 대상으로
   `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}` 패턴을 텍스트/바이너리 구분
   없이 검색(PowerShell `Select-String -Pattern ... -Encoding Byte`나 `strings.exe`류 도구).
2. 매치되는 각 후보 문자열의 payload(가운데 세그먼트)를 base64url 디코딩해 `"role":"service_role"`
   포함 여부만 확인(값 자체를 로그에 남기지 않고 **불리언 결과만** 출력).
3. 하나라도 발견되면 CI를 실패시켜 배포 자체를 막는다(`exit 1`).
4. 이 스캔은 `.env` 뿐 아니라 PyInstaller가 만든 `.pyz`/frozen 모듈, Launcher/Updater exe까지
   전부 대상으로 해야 함 — 코드 어딘가에 하드코딩된 폴백 값이 있을 가능성도 같이 걸러짐.
5. 스캐너 자체는 `tools/scan_release_secrets.ps1` 같은 신규 스크립트로 제안하며, **이번 Stage 0
   보고서 단계에서는 설계만 제시하고 구현/실행은 하지 않았습니다** (지시사항 "코드 변경 전
   상세 보고" 준수).

---

## 10. 회귀 테스트 목록 (Phase 1~3 진행 중 각 단계마다)

- 로그인 / 로그아웃 / 세션 재개(`sync_auth`)
- 회원가입 전체 플로우(약관 동의 → 이메일 인증코드 → 가입 완료)
- 비밀번호 찾기/재설정
- 출금 신청 제출 + 출금 이력 조회 (금액 정확성까지)
- 영상 렌더링 후 토큰/payout 차감이 정확히 반영되는지
- 추천인 대시보드(트리, 커미션 타임라인), 추천인 출금 신청
- 프로젝트 기기 간 동기화(기기 A 생성 → 기기 B 재로그인 시 노출)
- 학습자료(NotebookLM) 동기화
- TTS 커스텀 보이스 목록 노출, 관리자 보이스 CRUD
- 음악 기획 템플릿 목록 노출
- 에셋 매칭 UI(자동/수동)
- 테넌트(화이트라벨) 관리자 패널 — 커미션율 변경, 워터마크 설정
- 주제 추천 피드 + 주제 클레임(작업 배정)
- 자동 게시 스케줄러 (스테이징 환경에서 최소 1회 트리거 확인)
- 원격 렌더 큐 등록/상태 갱신 (해당 워커가 실제 사용되는 경로라면)
- 기존 자동화 스위트 전체 재실행: `tests/test_script_style_*.py`,
  `tests/test_autopilot_pipeline.py`, `tests/test_project_music_integration.py` (공유 파일을
  건드리므로 무관해 보여도 필수)
- **클린 설치 시뮬레이션**: `%LOCALAPPDATA%`가 비어있는 상태에서 새로 설치한 것처럼 앱 최초
  구동 → 로그인 없이도 크래시 없이 로그인 화면까지 도달하는지 (service_role 없는 `.env`로도
  부팅 자체는 절대 실패하면 안 됨)
- 릴리즈 아티팩트 문자열 검사(§9) 통과

---

## 11. BLOCKER 목록 (요약, 실행 순서대로)

1. **[최우선, 시간 민감]** `ibnetsoft/AIR-releases`가 Public이라 이미 배포된 ~18개 릴리즈에
   현재 유효한 service_role 키가 공개 노출 중. 코드 이전과 무관하게 **즉시 키 재발급 여부를
   결정해야 함** (§CTO 결정 §1).
2. **[구조적]** service_role 사용이 `web_admin_client.py` 한 곳이 아니라 9개 파일에 흩어져
   있어(§3), "한 곳만 프록시로 바꾸면 끝"이 아니라 각 파일을 개별적으로 auth-web 프록시로
   바꿔야 함 — 규모가 AIR-0225 원안이 추정한 것보다 큼(로그인 잔여 호출 3곳 추가 확인, §3).
3. **[2차 경로]** `AIRStudio.spec`의 PyInstaller 자체 `.env` datas 항목(§1)도 별도로 제거해야
   로컬 빌드 경로까지 완전히 막힘 — `build_windows.ps1`만 고치면 CI는 안전해지지만 로컬 빌드는
   여전히 위험할 수 있음.
4. **[해결됨]** 원격 렌더 워커 확인 완료 — `services/remote_drive_render_service.py`,
   `services/render_queue_worker.py`는 `main.py`/`app/routers/video.py`/`app/routers/music.py`에서
   직접 호출되는 **메인 AIRStudio.exe의 실제 코드 경로**이므로 제거 대상에 포함. 반면
   `remote_drive_worker.py`(+`PicadiriRemoteWorker.spec`)는 별도 빌드/배포되는 운영자 전용
   GPU 워커 실행파일로, 공개 배포 파이프라인과 무관해 이번 Stage 0 범위 밖 (별도 하드닝 과제로
   분리 권장).
5. **[해결됨]** 데스크톱 내 관리자 추천인 라우터(`app/routers/admin_referrals.py`)는 이번 조사
   시점에 이미 존재하지 않음 — 이전 커밋 `0995bc7f "refactor: remove desktop app's
   admin_referrals module (CTO Priority 4)"`에서 삭제 완료됨. `main.py` 미등록, 템플릿/JS에
   잔여 링크 없음 확인. 추가 조치 불필요.

## 12. CTO 추가 결정 필요사항

1. **키 재발급 실행 시점**: Phase 0(§8)을 지금 바로 실행할지, 아니면 Phase 1 코드 이전을 먼저
   일정 부분 진행한 뒤 재발급할지. (조사자 의견: 이미 공개 노출된 값이므로 코드 이전을 기다릴
   이유가 없다고 판단하나, 재발급 실행 자체와 그 타이밍은 명시적으로 CTO 승인 대상이라고
   지시받았으므로 실행하지 않고 여기 올립니다.)
2. **Phase 1 진행 방식**: AIR-0225가 제안한 "한 기능씩 이전 → 빌드검증 → 커밋 → 배포 → 확인"
   사이클을 그대로 따를지, 이번 조사로 범위가 커진 만큼(9개 파일, ~25개 기능) 순서/배치를
   조정할지.
3. ~~원격 렌더 워커 3파일의 실행 위치~~ — **해결됨**, BLOCKER #4 참고.
4. ~~`admin_referrals.py`(데스크톱 내 추천인 관리) 폐기 여부~~ — **해결됨**, 이미 삭제되어 있음
   (BLOCKER #5 참고). 추가 결정 불필요.
5. **`SUPABASE_SERVICE_ROLE_KEY` 시크릿의 2026-07-11 수정 이력의 경위 확인** — 이번 세션에서
   제가 값을 바꾼 적은 없음(사실관계만 보고). AIR-0225B 긴급 대응으로 이 시크릿 자체는 이후
   완전히 삭제 처리됨(별도 인시던트 보고서 참고).
6. **§4 표의 "anon key + RLS로 대체 검토" 항목들**(음악 템플릿, QA 설정값 등 읽기 전용 성격)을
   auth-web 프록시 대신 진짜 anon-key 직접 호출로 갈지 — 이 경우 Python 쪽에 anon key 개념을
   신규로 도입해야 하므로 별도 설계가 필요함.

## Files Changed
- 없음 (조사/보고서만, 신규 문서 1개: 이 파일)

## Commit Hash
`pending` (아직 커밋하지 않음 — 커밋 여부도 지시 대기)
