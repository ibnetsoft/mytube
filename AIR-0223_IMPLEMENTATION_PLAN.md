# AIR-0223 — Referral Admin Dashboard: Implementation Plan

**Scope discipline restated up front**: this builds UI + the minimum new API surface needed to expose data that already exists (AIR-0221 Stage 1/2's `referral_commissions`/`referral_withdrawals`/`referral_audit_logs`, plus existing `profiles`/`global_settings`). No new referral business logic, no Stage 3 cutover of any *existing* read path, no Gen 2/3 touch, no change to how commissions are generated or how the Stage 2 dual-write behaves.

## 0. What already exists in `auth-web` (researched before writing any code)

| Existing asset | What it does | Reused how |
|---|---|---|
| `auth-web/app/api/admin/_auth.ts` | `requireAdmin`/`requireSuperAdmin`/`isAuthResponse`, `isSubAdmin` = `app_metadata.role === 'sub_admin'` (an already-real "country manager" concept) | Every new API route uses this unchanged. Reads use `requireAdmin` (lets country managers see their own scope); the two money-affecting actions (withdrawal approve/reject) use `requireSuperAdmin`, matching the existing precedent in `settlements/payout/route.ts`. |
| `auth-web/app/api/admin/referrals/route.ts` (GET/PATCH) | GET: builds a profile tree with country-scoped visibility, using **token-usage-based estimated commissions at hardcoded 5%/2% rates** (the "6b" projection figure from `CONSOLIDATION_PLAN.md` §4.6). PATCH: updates `country_code`/`referral_country`/`commission_rate` on a profile, and can flip `app_metadata.role = 'sub_admin'` + `managed_country` — i.e., **Country Manager assignment already has a working API**, just no UI surfaces it today. | GET's visibility-scoping *pattern* (country filter, superadmin-vs-scoped) is reused conceptually in the new Organization endpoint, but its commission numbers are **not** reused — they're the legacy estimate, not `referral_commissions`, and this ticket requires "AIR-0221에서 구축한 데이터 모델을 사용" instead. The PATCH endpoint **is reused as-is** for the Settings tab's Country Manager section — zero new code for that part. |
| `auth-web/app/admin/settings/referral/page.tsx` + `.../api/admin/settings/referral/route.ts` | Full working settings page for `referral_mode`/`referral_default_sponsor_uuid`/`referral_level1_percent`/`referral_level2_percent`/`referral_min_payout`/`referral_cycle`. Plain Tailwind, no external UI kit. | Settings tab **links to this page directly** rather than rebuilding it — "실제 저장 로직 변경은 하지 않는다" is satisfied trivially by not touching it at all. |
| `auth-web/app/admin/settlements/page.tsx` | Referral settlements list + "Approve & Pay" button. **Currently does not compile** — imports `@/components/ui/card` and `@/components/ui/button`, and no `components/ui/*` directory exists anywhere in this repo (confirmed via search). This is a pre-existing break, unrelated to AIR-0223. | Not reused, not fixed (out of scope) — but this confirms the safe pattern for new pages is **plain Tailwind + `useState`/`fetch`**, matching `settings/referral/page.tsx`, not the broken shadcn-style import pattern. |
| `auth-web/app/api/admin/withdrawals/route.ts` | Gen-0 **general wallet** `withdrawals` table admin actions (AIR-0221A-hotfixed). Different table entirely from `referral_withdrawals`. | Not reused — wrong table. Zero web-admin API exists today for `referral_withdrawals`/`referral_audit_logs`; both get new routes (justified: "꼭 필요한 경우"). |
| `app/routers/admin_referrals.py` (Python/FastAPI, desktop-app admin surface, not `auth-web`) | AIR-0221 Stage 2's `_stage2_dual_write_withdrawal_transition` — the canonical pattern for approve/reject: update legacy `referral_commissions` WITHDRAWAL row → mirror onto `referral_withdrawals` (via `metadata->>legacy_commission_id` lookup) → write `referral_audit_logs` rows for each state transition. | **Ported to TypeScript** (not called cross-language) as the same logic, for the web admin's withdrawal actions — see §5. This keeps both admin surfaces (desktop app, web admin) writing through the identical pattern instead of inventing a second, divergent one. |

## 1. Route map (all new, under `auth-web/app/admin/referrals/`)

```
/admin/referrals                    Dashboard (KPI cards + top sponsor/country/worker)
/admin/referrals/organization        Tree/Table org view
/admin/referrals/members/[id]        Member detail
/admin/referrals/commissions         Commission list + CSV
/admin/referrals/withdrawals         Withdrawal management (approve/reject)
/admin/referrals/audit               Audit log viewer
/admin/referrals/settings            Thin page: links to the existing settings page + Country Manager section (reuses /api/admin/referrals PATCH)
```
A shared `layout.tsx` provides the tab nav across all seven. Plain Tailwind throughout, matching the one page in this app that actually compiles.

## 2. API map (all new, under `auth-web/app/api/admin/referrals/`)

| Route | Method | Backs | Auth |
|---|---|---|---|
| `dashboard/route.ts` | GET | KPI cards + top sponsor/country/worker | `requireAdmin` |
| `organization/route.ts` | GET | Tree/table, search/filter/sort/pagination | `requireAdmin` |
| `members/[id]/route.ts` | GET | Member detail | `requireAdmin` |
| `commissions/route.ts` | GET | Commission list, filters, pagination (CSV done client-side from loaded rows — see §6) | `requireAdmin` |
| `withdrawals/route.ts` | GET | Withdrawal list, filters, pagination | `requireAdmin` |
| `withdrawals/[id]/route.ts` | PATCH | Approve/reject (mirrors Stage 2's Python helper — see §5) | `requireSuperAdmin` |
| `audit/route.ts` | GET | Audit log list, filters | `requireAdmin` |

No route touches `commissions`, `withdrawal_requests`, `worker_jobs`, `risk_flags`, `user_activity`, `user_events`, or any Gen 2/3 RPC. No route writes to `referral_commissions`'s core generation logic (`commission_tokens`/`rate_percent`/`status='pending'`→auto-paid semantics) — that remains exactly what Stage 2 built, untouched.

## 3. Dashboard — data mapping

| KPI | Query |
|---|---|
| Total / Level1 / Level2 Referral Members | `profiles` count where `referred_by IS NOT NULL` (L1: `referred_by` points to *any* profile; L2 requires walking one more hop — computed in-memory from the same profile set the Organization endpoint already builds, not a second heavy query) |
| Today's / Monthly Commission | `SUM(commission_tokens)` from `referral_commissions` where `status='paid'`, `created_at` within today / current calendar month |
| Total Paid Commission | `SUM(commission_tokens)` where `status='paid'` and `commission_type != 'WITHDRAWAL'` (excludes the negative withdrawal-ledger rows from the "earned" total) |
| Total Withdrawal Requested / Completed | `COUNT(*)`/`SUM(amount)` from `referral_withdrawals` grouped by `status` (REQUESTED+APPROVED+SENDING = "requested/in-flight", COMPLETED = completed) |
| Top Sponsor | `beneficiary_id` with highest `SUM(commission_tokens)` (paid, non-withdrawal rows), joined to `profiles` for display name |
| Top Country | `profiles.referral_country` (fallback `country_code`) with the highest member count among referred (`referred_by IS NOT NULL`) profiles |
| Top Worker | `source_user_id` with highest `SUM(commission_tokens)` generated for their sponsor(s) — i.e. the referred user whose activity produced the most commission |

All of this reads `referral_commissions`/`referral_withdrawals`/`profiles` directly — the AIR-0221 data model, per the ticket's "중요 원칙." None of it reads the legacy `/api/admin/referrals` estimate.

## 4. Organization — Tree/Table, search/filter/sort/pagination

Reuses the **pattern** (not the code) from `/api/admin/referrals`: fetch all `profiles` with referral-relevant columns, scope visibility by `referral_country`/`country_code` for non-superadmin (country manager) requesters, build a `referred_by` parent→children map for L1/L2. Real commission totals per member come from a single grouped `referral_commissions` query (by `beneficiary_id`, split by `commission_level`), not the token-usage estimate.

- **Tree View**: nested L1→L2 rendering off the same in-memory structure.
- **Table View**: flat list of the same rows, sortable client-side (small dataset expected at this stage — no real production referral data exists yet per the Stage 2 bake-watch baseline).
- **Search**: name/email/referral code — substring filter, server-side (`ilike`) since it's a single indexed-ish query, not per-row client filtering.
- **Filters**: country (`referral_country`/`country_code`), signup date range (`created_at`), activity (defined here as "has at least one `referral_commissions` row" — the closest honest proxy to "활동여부" without inventing a new activity-tracking concept, which would be new business logic and out of scope).
- **Sort**: signup date / referral count / commission total — server-side `ORDER BY` where the field is a direct column, in-memory sort where it's a derived aggregate (referral count, commission total).
- **Pagination**: standard offset/limit via PostgREST `range`/`limit`/`offset`, `Prefer: count=exact` for total-count-aware paging.

## 5. Member Detail

`GET /api/admin/referrals/members/[id]` returns: basic profile info, referrer (`referred_by` resolved to a profile), own referral code, L1 members (direct `referred_by = id`), L2 members (one hop further), this-month / cumulative job count (from `publishing_requests` where `user_id = id` and `status = 'approved'`, date-bucketed — the closest existing "작업" signal, consistent with AIR-0221D's identification of publish-approval as the job-completion proxy), this-month / cumulative referral commission (`referral_commissions` sums, date-bucketed), available withdrawal balance (same computation `app/routers/referral.py`'s `get_referral_withdrawal_info` already uses — mirrored here, not reinvented: `paid earned − completed/pending withdrawals`), withdrawal history (`referral_withdrawals` for this user), and recent jobs (`publishing_requests`, last N).

## 6. Commission — list, filters, CSV

`GET /api/admin/referrals/commissions` — filters: `commission_level` (1/2), date range, member search (by beneficiary or source user). Sort: date/amount. Pagination: same offset/limit pattern as Organization.

Displayed columns map 1:1 to real columns, per the Commission Trace design already specified in `CONSOLIDATION_PLAN.md` §10.3/§10.4: 발생일 = `created_at`, 원인 Job = `source_job_id`, Net Settlement Amount = `base_tokens` **labeled honestly** (see note below), 적용% = `rate_percent`, 수당 = `commission_tokens`, 상태 = `status`.

**Honest note, not glossed over**: `base_tokens` is still the recharge amount today, not a true Net Settlement Amount — per `AIR-0221D_REFERRAL_ACTIVATION_PLAN.md`, Net Settlement Amount's real definition is deferred to a future Settlement Engine Specification and hasn't been implemented. This dashboard displays whatever is actually in `base_tokens` under the "Net Settlement Amount" column header (since that's the field the ticket's Commission section maps it to and the column the CTO's data model already reserved for it), with a UI tooltip/caption noting it reflects the pre-Settlement-Engine figure — not silently pretending the deferred calculation already exists.

**CSV Export**: generated client-side from the currently-loaded (filtered/paginated) row set via a `Blob`/`download` attribute — no new server endpoint, no dependency added. Limitation stated plainly in the UI and in `AIR-0223_QA.md`: this exports the current page's loaded rows, not a server-side full-dataset export — reasonable given the data volumes real production referral data is expected to have at this stage (none yet, per Stage 2 bake-watch baseline), and avoids introducing a new streaming/export API surface not asked for.

## 7. Withdrawals — status management

`GET /api/admin/referrals/withdrawals` — list + filters (status, date, member) + pagination, reading `referral_withdrawals` directly (this is its whole purpose — the canonical mirror table).

`PATCH /api/admin/referrals/withdrawals/[id]` — approve/reject. **This ports the exact logic of `app/routers/admin_referrals.py`'s `_stage2_dual_write_withdrawal_transition`, in TypeScript, operating on the same tables**:
1. Look up the `referral_withdrawals` row by `id` (the URL param — this route operates on the *new* table directly, since that's what the web admin list is browsing).
2. Find the linked legacy `referral_commissions` row via `metadata->>'legacy_commission_id'` (reverse of the lookup direction used in the Python helper, since here we start from the new table, not the legacy one).
3. Update the legacy `referral_commissions` row's `status` (`COMPLETED`/`REJECTED`) — same values, same table, same semantics Stage 2 already established, so the legacy path (still authoritative per Stage 2 design) reflects the action too, not just the mirror.
4. Update `referral_withdrawals.status` through the same `APPROVED→SENDING→COMPLETED` (approve) or `REJECTED` (reject) sequence as the Python helper, with matching timestamps.
5. Write one `referral_audit_logs` row per transition (`approved`/`sending`/`completed`, or `rejected`), `actor_id` = the requesting admin's `id` (`requester.user.id`), `metadata.legacy_commission_id` for cross-reference.

If no legacy row is found (shouldn't happen for rows created via the dual-write path, but defensively handled): the action still updates `referral_withdrawals` and logs the audit trail, with `metadata.legacy_commission_id: null` and a note — matching how the Python helper already handles its own "mirror not found" case symmetrically.

This is **not** a new business rule — it is the Stage 2 rule, reimplemented so the web admin can trigger it too. Stage 3 cutover (making `referral_withdrawals` the sole system of record and dropping the legacy write) is explicitly **not** done here — step 3 above is what keeps this compliant with "Stage3 금지."

## 8. Audit — viewer

`GET /api/admin/referrals/audit` — filters: `entity_type`, `action` (매핑: 추천수당 생성→`generated`, 출금요청→`requested`, 승인→`approved`, 거절→`rejected`, Sending→`sending`, Completed→`completed`), member (via `actor_id` or by resolving `entity_id` back to a withdrawal/commission's owning member), date range, admin (`actor_id`). Pure read, no write path — the writes into this table already happen from Stage 2's code and this ticket's new §7 route; this tab only displays them.

## 9. Settings tab

A thin page: embeds a link to `/admin/settings/referral` (existing, unmodified) for Mode/Level%/Default Sponsor/Min Payout/Cycle, plus a **Country Manager** section that is new UI only, calling the **existing** `/api/admin/referrals` PATCH (`make_country_manager`, `managed_country`) — zero new save logic, satisfying "실제 저장 로직 변경은 하지 않는다. 기존 global_settings API를 사용한다" for the settings-value part, and reusing the already-implemented-but-unsurfaced country-manager assignment API for the country-manager part.

## 10. UX baseline applied to every list (Organization/Commission/Withdrawals/Audit)

Search input (debounced), filter controls, offset/limit pagination with page indicator, loading skeleton/spinner state, empty-state message, responsive (Tailwind grid/flex breakpoints, no fixed-width layouts) — implemented once as shared conventions across the pages rather than a shared component library (there isn't one in this repo — see §0's `components/ui` finding — introducing one is bigger scope than this ticket needs).

## 11. Explicit non-goals (restated from the ticket, held to literally)

- No Settlement Engine implementation, no Net Settlement Amount calculation change (§6's honest-label note is the extent of engagement with that gap).
- No Job-Completed trigger implementation (AIR-0221D's open item, untouched here).
- No Stage 3 read cutover of `app/routers/referral.py`/`admin_referrals.py`/`auth-web/lib/settlement.ts` — those remain exactly as Stage 2 left them; this dashboard is a *new* consumer of the new tables, not a migration of an *existing* one.
- No Gen 2/3 object read, written, or referenced.
- No change to `referral_commissions` generation logic, `commission_level`/`source_job_id` population, or the dual-write mechanics themselves (only their *display*, and — for withdrawals — a second UI trigger for the *same already-defined* transition, per §7).
