# AIR-0225 — Service Role Key 직접 사용 기능 목록 및 프록시 이전 계획

CTO 우선순위 지시 [AIR-0224A 이후 우선순위] 6·7·8번에 대한 산출물.

## 배경

`services/web_admin_client.py`가 `SUPABASE_SERVICE_ROLE_KEY`(RLS 우회, DB 전체 접근 가능)로
Supabase REST API를 **데스크톱 앱에서 직접** 호출하는 구조. 로그인(`desktop_login`)만
2026-07-09에 `auth-web`의 `/api/desktop-login`으로 이전 완료 — 이 함수는 더 이상 이 키를
필요로 하지 않음. 그 외 전부는 여전히 이 키가 배포된 앱 안에 그대로 있어야 동작한다.

## 1. 현재 이 키를 직접 쓰는 기능 목록 (호출 횟수순)

| 파일 | 호출 수 | 기능 영역 | 비고 |
|---|---|---|---|
| `app/routers/settings.py` | 24 | API 키 설정, **출금 신청/이력**, 정산 요약/내보내기, 스타일 프리셋, 언어, 오토파일럿, 웹툰 규칙 | 가장 넓은 영역. 출금(`/api/withdrawal/request`)은 금전적으로 민감 |
| `app/routers/auth.py` | 17 | 회원가입, 비밀번호 찾기/재설정, 이메일 인증 (로그인만 이전 완료) | 로그인과 동일한 성격 — 우선 이전 대상 |
| `app/routers/admin_tenant.py` | 12 | 테넌트(멀티브랜드) 관리자 기능, 커미션율 설정 | 관리자 전용이라 상대적으로 노출 빈도 낮음 |
| `services/auth_service.py` | 8 | 라이선스 검증(`/api/verify` 경유 — 이미 부분적으로 서버 프록시화됨), 잔액 동기화 | `resolve_user_id`만 직접 호출, 나머지는 이미 `/api/verify` 경유 |
| `services/project_sync_service.py` | 8 | 프로젝트 메타데이터 동기화 | |
| `app/routers/admin_referrals.py` | 6 | 데스크톱 앱 내 관리자용 추천인 대시보드 | 이번에 커밋한 auth-web 쪽 UI(AIR-0223)와 기능 중복 — 추후 auth-web으로 완전 이관 시 이 라우터 자체가 불필요해질 수 있음 |
| `app/routers/referral.py` | 5 | 추천코드 검증, 추천인 연결 | |
| `services/auto_publish_service.py` / `services/sync_service.py` | 4 each | 자동 게시, 일반 동기화 | |
| `services/learning_sync_service.py` | 4 | 학습자료(NotebookLM) 동기화 | |
| `app/routers/admin_voices.py` | 3 | TTS 음성 관리 | |
| `app/routers/asset_matching_api.py`, `services/storage_service.py` | 2 each | 에셋 매칭, 스토리지 | |
| `app/routers/music.py`, `tts.py`, `user_topics.py`, `video.py`, `voices.py`, `services/qa_service.py`, `services/topic_queue_sync_service.py` | 1 each | 음악/TTS/영상 생성, 주제, QA, 큐 동기화 | 호출은 적지만 **영상 생성 토큰 차감**(`video.py`)은 금전적으로 민감 |

## 2. 특히 민감한 지점 (우선 이전 대상)

1. **`app/routers/settings.py`의 출금 신청/이력** — `submit_withdrawal_request`, `get_withdrawal_history` — 유저 자산 이동과 직결.
2. **`app/routers/video.py`의 토큰 차감** — 과금 로직.
3. **`app/routers/admin_tenant.py`의 커미션율 변경** (`update_tenant_commission`) — 관리자 전용이지만 금전 설정.
4. **`app/routers/auth.py`의 회원가입/비밀번호 재설정** — 로그인과 동일 계열, 이미 만들어둔 `auth-web` 프록시 패턴을 그대로 재사용 가능해서 구현 비용이 가장 낮음.

## 3. 이전 작업 계획 (auth-web 프록시 패턴 재사용)

로그인에서 이미 검증된 패턴을 그대로 반복 적용:

1. `auth-web/app/api/desktop/<feature>` 라우트 신규 작성 — 서버 쪽에서 `SUPABASE_SERVICE_ROLE_KEY`로 실제 로직 수행.
2. `services/web_admin_client.py`에 대응하는 `requests.post(f"{self.dashboard_url}/api/desktop/<feature>", ...)` 메서드 추가.
3. 데스크톱 앱 라우터(`app/routers/*.py`)는 이 새 메서드만 호출하도록 교체.
4. 매 건마다 `next build` 전체 통과 확인 후 커밋 (오늘 세션에서 실제로 매번 이렇게 검증함 — 로컬 빌드 통과 ≠ 커밋된 의존성까지 전부 존재함을 보장하지 않는다는 점을 오늘 직접 겪었으므로, **커밋 전 반드시 관련 없는 로컬 미커밋 변경분을 stash 하고 빌드 재검증** 하는 절차를 표준화 권장).

## 4. 단계별 우선순위 제안

| 순서 | 대상 | 예상 영향도 | 이유 |
|---|---|---|---|
| 1 | `auth.py` 회원가입/비밀번호 재설정 | 낮음 (구현 비용) / 중간 (리스크) | 로그인과 동일 패턴 재사용, 가장 빠르게 처리 가능 |
| 2 | `settings.py` 출금 신청/이력 | 높음 | 금전적으로 가장 민감, RLS 우회 키 유출 시 피해 최대 |
| 3 | `video.py` 토큰 차감 | 높음 | 과금 정확성과 직결 |
| 4 | `admin_tenant.py` 커미션율 등 관리자 기능 | 중간 | 관리자만 접근하지만 설정값이 금전에 영향 |
| 5 | 나머지 조회/동기화 위주 기능 (프로젝트 동기화, 학습자료, 음악/TTS 등) | 낮음 | 대부분 읽기 위주라 상대적으로 리스크 낮음, 일괄 처리 가능 |
| 6 | `admin_referrals.py` (데스크톱 내 관리자 추천인 대시보드) | 낮음 (제거 검토) | AIR-0223으로 auth-web에 동일 기능이 이미 구축됨 — 이전보다는 **중복 제거(데스크톱 라우터 자체 폐기)** 검토가 더 적절할 수 있음, 별도 논의 필요 |

## 5. 진행 방식 관련 제안

- 한 번에 전체를 이전하기보다, 위 순서대로 **한 기능씩** 이전 → 빌드 검증 → 커밋 → 배포 → 실제 동작 확인의 사이클을 반복하는 것을 권장 (오늘 로그인 이전 때 실제로 이 방식으로 진행해서 배포 중 발견된 문제 3건을 그때그때 잡을 수 있었음).
- 항목 1(회원가입/비밀번호 재설정)은 규모가 작고 위험도도 감당 가능한 수준이라, 승인 시 바로 다음 작업으로 착수 가능.
