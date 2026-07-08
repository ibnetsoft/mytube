# AIR-0205: Referral Growth Loop Notification System
**Status**: COMPLETED & APPROVED
**Priority**: CRITICAL
**Role**: Senior Backend & Frontend Engineer

## Objective
Turn the referral system into a continuous growth loop by notifying users when specific events occur within their referral network. This encourages active engagement and increases the "wow" factor for referrers when they see their organization growing.

## Architecture Decisions
Per CTO architecture approval:
- Use **DB Trigger** as primary notification generator. API-level event creation was prohibited.
- Unique index `(user_id, type, reference_id)` used to prevent duplicate notifications (idempotency).
- Use **FastAPI Background Task** for re-engagement instead of `pg_cron`.

## Changes Implemented

### 1. Database (Supabase / Postgres)
- **Table**: `public.user_notifications`
  - Columns: `id`, `user_id`, `type` (ENUM), `reference_id`, `title`, `message`, `is_read`, `created_at`
  - Unique Constraint: `idx_user_notifications_dedup` on `(user_id, type, reference_id)`
- **Triggers**:
  - `REFERRAL_JOIN`: Triggered on `profiles` when a new referral joins.
  - `MILESTONE`: Triggered on `profiles` when a user reaches 5, 10, 50, 100 referrals.
  - `COMMISSION_EARNED`: Triggered on `commissions` for each completed job by a downline.
  - `FIRST_REWARD`: Triggered on `commissions` for the very first reward.
- **RPC Update**: 
  - `get_referral_dashboard_kpi` updated to fetch and attach an array of `user_notifications` (up to 50 latest) to the KPI JSON object.
- **RPC for Re-engagement**:
  - `trigger_reengagement_notifications()` created to flag inactive users (> 7 days) who have active growing downlines.

### 2. Backend API (FastAPI & Next.js)
- **FastAPI Background Task**: 
  - Created `ReferralEngagementService` (`app/services/referral_engagement_service.py`) running every 24 hours.
  - Executed on startup via `asyncio.create_task` in `main.py`.
- **Next.js APIs**: 
  - `GET /api/user/notifications/route.ts` - Fetch latest notifications
  - `POST /api/user/notifications/read/route.ts` - Mark notifications as read

### 3. Frontend (Next.js / React)
- **Notification Center**: Created `NotificationDropdown.tsx` for the Referral Dashboard.
- **Dashboard Integration**: Added the `NotificationDropdown` to the header of `UserReferralDashboard.tsx`.
- **Badge Synchronization**: Modified `UserReferralDashboard.tsx` to dynamically parse the returned notifications from KPI, and reflect the true unread count back into the `base.html` sidebar badge (`#referral-badge`).

## Testing Done
- Checked SQL migrations via `scratch/apply_0205_migration.py`.
- Validated triggers and `get_referral_dashboard_kpi` response.
- Background worker correctly instantiated in FastAPI.
- Frontend properly renders dropdown and clears notifications.

## Next Steps
- Verify in Staging with actual user generation and commission flows.
- Review notification copy for A/B testing and marketing improvements.
