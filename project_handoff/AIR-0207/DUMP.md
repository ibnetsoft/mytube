# AIR-0207: Monetization Optimization & A/B Testing System
**Status**: COMPLETED & APPROVED
**Priority**: CRITICAL
**Role**: Senior Backend & Data Engineer

## Objective
Establish an initial monetization and optimization framework by introducing an event tracking system, tracking funnel conversion rates, and building an A/B testing structure for the referral layer.

## Architecture & Constraints Addressed
Per CTO Data Integrity Rules:
- **Metrics Dashboard Privacy**: Hosted exclusively at `/admin/metrics`. It is completely separated from the user-facing `/referrals` dashboard.
- **A/B Testing Determinism**: Created a highly efficient, deterministic frontend hook (`useABTest.ts`) that strictly yields a 50/50 split (A/B) across users without needing server roundtrips or DB assignments.
- **Data Integrity / Duplicate Prevention**: All backend events utilize DB triggers feeding into `user_events`. Added a strict unique constraint `(user_id, event_type, reference_id)` to block all duplicates.
- **Strict Funnel Enforcement**: The conversion funnel exactly tracks the CTO-mandated sequence:
  `VIEW_REFERRAL_PAGE` ➔ `COPY_LINK` ➔ `REFERRAL_JOIN` ➔ `JOB_COMPLETED` ➔ `COMMISSION_EARNED`.
- **Scope Limit**: The experiment currently exclusively tests the **Referral CTA Copy** (`링크 복사` vs `💰 복사하고 수익 창출`).

## Implementation Details

### 1. Database (Supabase)
- **`user_events` Table**: Tracks all behavioral telemetry with high-performance indices on `created_at`, `user_id`, and `event_type`.
- **Triggers**: Database-level PL/pgSQL functions on `profiles` (for Joins), `worker_jobs` (for Completion), and `commissions` (for Earning) ensure atomic, tamper-proof backend tracking.
- **RPC (`get_analytics_dashboard`)**: An aggregation function running in Postgres that natively calculates funnel drop-off counts, parses JSON metadata for A/B variant performance, and ranks top referrers by volume and revenue.

### 2. API & Telemetry
- **`POST /api/user/events`**: The frontend telemetry pipeline used strictly for tracking top-of-funnel actions (`VIEW_REFERRAL_PAGE`, `COPY_LINK`). Deduplication is managed via MD5 hashing the user + date (to prevent refreshing from blowing up pageviews) combined with the DB unique constraint.
- **`GET /api/admin/metrics`**: The secure admin conduit to pull the RPC data into the dashboard.

### 3. Frontend
- **ReferralShareCenter**: Wrapped the "Copy Link" CTA in `useABTest`. Sends telemetry containing `{ variant: 'A|B' }` back to the events API.
- **Metrics Dashboard**: A beautiful, modular Next.js page at `/admin/metrics` displaying:
  1. The 5-stage Referral Conversion Funnel with step-by-step drop-off percentages.
  2. The A/B Experiment Hub (currently tracking CTA performance by grouping `VIEW_REFERRAL_PAGE` and `COPY_LINK` rates by variant).
  3. The Top Referrers Leaderboard.

## Expected Revenue Impact
By moving from a "guesswork" based UI to a data-driven model, we can definitively prove if adding an emoji + "Earn" phrasing to the CTA directly increases link sharing. If Variant B increases `COPY_LINK` events by 20%, we can confidently extrapolate a downstream increase in `REFERRAL_JOIN` and `COMMISSION_EARNED`, pushing the 90/10 rollout into production to permanently elevate the revenue floor.
