# AIR-0223 — QA

## Scope of verification actually performed

This environment has no authenticated admin session (no Supabase login), so a true end-to-end click-through (log in as superadmin, browse each tab, approve/reject a real withdrawal) was **not possible** — same limitation noted throughout every prior AIR-0221 sub-ticket in this project. What follows is everything that *could* be verified without one, done as thoroughly as possible to compensate.

## 1. Static verification

- `npx tsc --noEmit` — **zero errors** in any AIR-0223 file (7 pages, 1 layout, 2 shared helper files, 7 API routes, 1 shared API helper).
- `eslint` (scoped to `app/admin/referrals/**` and `app/api/admin/referrals/**`) — 4 errors found and fixed (unescaped `"`/`'` in JSX text, `react/no-unescaped-entities`), **zero errors after fix**.

## 2. Full production build — attempted, fails for reasons unrelated to AIR-0223

`npm run build` fails, but on four `Module not found` errors, **none of which are in any file this ticket touched**:
- `app/admin/settlements/page.tsx` — imports `@/components/ui/card`/`button`. **Pre-existing**: confirmed via `find` that no `components/ui/` directory exists anywhere in this repo. This page has been broken independent of AIR-0223 (discovered while researching AIR-0223's implementation plan, not caused by it).
- `app/api/admin/settings/referral/route.ts` — missing `@supabase/auth-helpers-nextjs` package. Pre-existing, unrelated.
- `app/api/admin/users/recharge/route.ts` — `Can't resolve '../../../../lib/settlement'`. Pre-existing path bug (the relative path is one `../` short of reaching `auth-web/lib/settlement.ts` from that file's location) — this file was never touched by AIR-0223 or any earlier ticket this session.

`next.config.mjs` already has `eslint.ignoreDuringBuilds: true` and `typescript.ignoreBuildErrors: true` (pre-existing, not set by this work) — confirms this app has known, accepted build fragility independent of this ticket. None of it is fixed here (out of scope — AIR-0223 is UI/admin functionality only).

## 3. Dev-server smoke test (real compilation + real request/response, not just static analysis)

Started `npm run dev`, hit every new route with `curl`, then stopped the server. Every single new file compiled successfully under Next's own dev compiler and produced the expected HTTP response — this is stronger evidence than `tsc`/`eslint` alone since it exercises Next's route resolution, the `_auth.ts` middleware chain, and actual module loading at runtime:

| Route | Method | Result |
|---|---|---|
| `/api/admin/referrals/dashboard` | GET (no auth header) | `403` (expected — `requireAdmin` correctly rejecting) |
| `/api/admin/referrals/organization` | GET | `403` (expected) |
| `/api/admin/referrals/commissions` | GET | `403` (expected) |
| `/api/admin/referrals/withdrawals` | GET | `403` (expected) |
| `/api/admin/referrals/withdrawals/[id]` | PATCH | `403` (expected) |
| `/api/admin/referrals/audit` | GET | `403` (expected) |
| `/api/admin/referrals/members/[id]` | GET | `403` (expected) |
| `/admin/referrals` (Dashboard) | GET | `200` |
| `/admin/referrals/organization` | GET | `200` |
| `/admin/referrals/commissions` | GET | `200` |
| `/admin/referrals/withdrawals` | GET | `200` |
| `/admin/referrals/audit` | GET | `200` |
| `/admin/referrals/settings` | GET | `200` |
| `/admin/referrals/members/[id]` | GET | `200` |

Dev server log confirmed a clean `✓ Compiled ... (N modules)` line for every one of these with **zero errors attributed to any AIR-0223 file** — the only error in the whole log (`TypeError: Cannot read properties of undefined (reading 'os')`) is the pre-existing lockfile-patch warning that appears on every `next dev`/`next build` invocation in this repo regardless of what code changed, confirmed non-fatal to dev-server operation (server still reached `✓ Ready`).

Pages return `200` even without auth because — consistent with the rest of this app's admin pages (`components/DashboardContent.tsx`) — auth is enforced **client-side** (the page shell renders, then `useAuthToken()` resolves no session, then every API call correctly gets `403` and the page shows its error state). This is the existing app-wide pattern, not something introduced here.

## 4. What could not be verified (honest gaps)

- **Real data flow end-to-end**: per `worknote/AIR-0221-Stage2-BAKE.md`'s baseline (still current — `referral_mode` is still `OFF` per `AIR-0221D`), there is **zero real data** in `referral_commissions`/`referral_withdrawals`/`referral_audit_logs` in production. Every list/dashboard page will correctly show its empty state today. The KPI math, JOIN logic, and CSV export were verified by code review against the exact column names/types in the Stage 1/2 schema (cross-checked against `migrations/air_0221_referral_stage1_foundation.sql`), not against real rows — this is the honest limit of what "correct" can mean before real data exists.
- **Approve/reject action's actual write behavior**: the `withdrawals/[id]/route.ts` PATCH logic was verified by close comparison against `app/routers/admin_referrals.py`'s `_stage2_dual_write_withdrawal_transition` (same transition sequences, same table targets, same audit-log shape) but was not exercised against a real `referral_withdrawals` row with a real linked legacy `referral_commissions` row, since none exist yet.
- **Country Manager assignment**: the Settings tab's calls into the existing `/api/admin/referrals` PATCH endpoint were verified by reading that endpoint's code (unchanged, confirmed it accepts exactly the payload shape this new UI sends) but not exercised live.
- **Visual/responsive review**: no browser was used to actually look at the rendered pages (this environment has no way to screenshot/view). Tailwind classes follow the same patterns as `settings/referral/page.tsx` (the one confirmed-working reference page in this app), but actual visual correctness (spacing, overflow, mobile breakpoints) is unverified.

## 5. Regression check on existing functionality

- `git diff --stat` confirms **zero existing files were modified** by AIR-0223 — every file is new (`app/admin/referrals/**`, `app/api/admin/referrals/**`, plus this doc and the implementation plan). The existing `/api/admin/referrals` route (GET/PATCH) is read-only reused, not edited. The existing `/admin/settings/referral` page/route is linked to, not edited.
- Since nothing existing was touched, regression risk is limited to: (a) route-namespace collisions — none, `admin/referrals/*` under `app/admin/` didn't exist before; (b) shared-module side effects — `_hooks.ts`/`_components.tsx`/`_shared.ts` are new, scoped files only imported by AIR-0223's own pages/routes, not by any existing code.
- No Stage 3 cutover: `app/routers/referral.py`, `app/routers/admin_referrals.py` (Python/desktop admin), `auth-web/lib/settlement.ts` are all untouched — the desktop-app admin surface and the settlement worker behave exactly as Stage 2 left them.
- No Gen 2/3 table, RPC, or route referenced anywhere in AIR-0223's code (confirmed by review — every query targets `profiles`, `referral_commissions`, `referral_withdrawals`, `referral_audit_logs`, `publishing_requests`, or calls the pre-existing `/api/admin/referrals` and `/api/admin/users` routes).

## 6. Known limitations carried into the delivered UI (documented, not silently hidden)

- **"Net Settlement Amount" column** (Commission tab) displays `base_tokens` (today's recharge-amount figure) with an explicit on-page caption stating the real calculation is deferred to a future Settlement Engine Specification — not glossed over as if it were already correct.
- **CSV Export** exports the currently-loaded/filtered page of rows, not a full server-side unpaginated export — stated in `AIR-0223_IMPLEMENTATION_PLAN.md` §6 and reasonable given there's no real data volume yet to make that limitation matter in practice.
- **Country Manager revocation**: the reused `/api/admin/referrals` PATCH endpoint only ever *sets* `role: 'sub_admin'`, never reverts it — the Settings tab's UI and its inline caption say this plainly rather than implying a working "revoke" button that the underlying (unmodified, out-of-scope) API doesn't actually support.
- **Activity filter** ("활동여부") is defined as "has at least one `referral_commissions` row" — the closest honest proxy without inventing a new activity-tracking concept (which would be new business logic, out of scope per the ticket's own "추천 시스템 로직 변경 금지").

## PASS criteria checklist (per the ticket's §11)

| Criterion | Status |
|---|---|
| 운영자가 웹어드민만으로 추천인 조직 조회 가능 | Built (`/admin/referrals/organization`), verified compiling/routing; not exercised against real data (none exists) |
| 회원별 추천현황 조회 가능 | Built (`/admin/referrals/members/[id]`), same caveat |
| Level1/Level2 수당 조회 가능 | Built (`/admin/referrals/commissions`, filter by level), same caveat |
| 추천수당 출금 관리 가능 | Built (`/admin/referrals/withdrawals`, approve/reject wired to the Stage-2-equivalent dual-write), same caveat |
| Audit 조회 가능 | Built (`/admin/referrals/audit`) |
| 검색/필터/페이지네이션 정상 | Implemented on every list route; server-side logic verified by code review + dev-server smoke test, not against real result sets |
| 기존 기능 Regression PASS | Confirmed via `git diff --stat` (zero existing files modified) + dev-server smoke test showing no new compile errors anywhere in the app attributable to this change |

**Overall**: all deliverables built and statically/dynamically smoke-tested clean. **Full functional sign-off is blocked on the same thing every AIR-0221 sub-ticket has been blocked on**: no real referral data exists yet (`referral_mode` still `OFF`), and this environment has no authenticated session to click through the UI manually. Recommend a real admin click-through once `referral_mode` activation (`AIR-0221D`) produces real data, or at minimum once someone with dashboard access can log in and browse each tab.
