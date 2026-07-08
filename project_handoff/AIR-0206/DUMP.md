# AIR-0206: Retention & Habit Loop System
**Status**: COMPLETED & APPROVED
**Priority**: HIGH
**Role**: Senior Backend & Product Engineer

## Objective
Transform user behavior from occasional usage into a daily habit through psychological rewards, daily activity tracking, and intelligent re-engagement reminders.

## Architecture Decisions & Behavior Tuning
Per CTO behavior tuning requirements:
- **Daily Goals**: The daily task goal is strictly `1 job`. Referrals are tracked but kept optional for maintaining the streak.
- **Reminders**: Habit reminders are highly targeted. They are sent *only* if the user was active yesterday but remains inactive today.
- **Streak Reset**: The streak is strictly consecutive. If a day is skipped, the streak resets to 0. It is not artificially maintained.
- **Notification Spam**: Status notifications for completed jobs or referrals are strictly clamped to `0 → 1` (the first instance of the day) to prevent notification fatigue.
- **Concurrency**: UPSERT on `user_activity` is guaranteed via `ON CONFLICT DO UPDATE` at the Postgres trigger layer. 

## Features Implemented

### 1. Database & Tracking System (Supabase / Postgres)
- **Table**: `public.user_activity`
  - Columns: `id`, `user_id`, `activity_date`, `jobs_completed`, `referrals_added`, `current_streak`
  - Constraints: Unique Index on `(user_id, activity_date)` to allow atomic UPSERT locking.
- **Streak Logic**: 
  - Calculated within a PL/pgSQL function triggered by inserts/updates to `worker_jobs` and `profiles`.
  - Checks if a `user_activity` row exists for `CURRENT_DATE - INTERVAL '1 day'`. If so, increments `current_streak`. If not, sets streak to `1` (reset).
- **Notification Rules (In-Trigger)**:
  - Emits `FIRST_REWARD` only on the exact integer transition `v_old_jobs = 0` and `v_new_jobs = 1`.
  - Emits `MILESTONE` only on exactly 3, 7, and 30 consecutive days.
- **KPI RPC Extension**: 
  - `get_referral_dashboard_kpi` was extended to return a user's `activity` (jobs, referrals, streak) automatically with their referral dashboard payload.

### 2. Backend Reminders (FastAPI & Next.js)
- **Reminder Logic**: Added a new DB RPC `trigger_habit_reminders()`.
  - Queries `user_activity` to find users active yesterday (`jobs_completed > 0` OR `referrals_added > 0`) who have no recorded activity for `CURRENT_DATE`.
  - Inserts a `SYSTEM_ALERT` notification urging them to complete a task.
- **Background Worker**: Hooked `trigger_habit_reminders()` into the `ReferralEngagementService` daily worker loop alongside the existing re-engagement alerts.

### 3. Frontend User Experience (Next.js)
- **Streak Widget**: Designed a premium, aesthetically-pleasing `StreakWidget.tsx`.
- **UX Improvements**:
  - Displays the `Current Streak` beautifully using the brand's indigo/glassmorphic theme.
  - Dynamically switches status between **"Pending"** (orange pulse) and **"Secured"** (green checkmark) based on whether `jobs_completed > 0`.
  - Displays a progress bar toward the next milestone: "Complete 1 job today to reach X days!".
- **Integration**: Placed directly at the top of the `UserReferralDashboard.tsx` for immediate visibility.

## Retention Impact
The system directly intercepts user churn on **Day 2**. By enforcing a strict daily cadence and gamifying the 1-job-a-day goal, we replace the dependency on manual email blasts with a self-sustaining psychological loop. Concurrency-safe DB triggers ensure the stats are always accurate, keeping the feedback loop tight.
