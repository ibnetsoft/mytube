# AIR-0158E: Withdrawal API Migration & RPC Handoff

## 1. Overview
The legacy `process_withdrawal_commission` RPC and standard `withdrawals` table have been successfully migrated to the new `withdrawal_requests` ledger format. The new withdrawal system now strictly calculates available balances based on verified `public.commissions` (Referral Commission Engine) rather than relying on legacy or easily desynchronized cache fields like `profiles.usdt_balance`.

## 2. Key Changes (Source of Truth)
- **Approved Commission Total**: Now derived exclusively from `public.commissions` where `status = 'APPROVED'`.
- **Locked Withdrawals Total**: Now derived from `public.withdrawal_requests` where `status IN ('REQUESTED', 'APPROVED', 'SENDING', 'COMPLETED')`.
- **Available Balance**: Computed atomically as `Approved Commission - Locked Withdrawals`.

## 3. Implementation Details
### Database (RPC Migration)
File: `migrations/air_0158e_withdrawal_rpc.sql`
- `public.get_available_withdrawal_balance(p_user_id)`: Calculates realtime available USDT.
- `public.request_withdrawal(p_amount, p_wallet_address)`: Atomically validates limits, prevents race conditions, checks for BEP20 wallet validity, and generates a new `withdrawal_requests` row.

### User API (`auth-web/app/api/user/withdrawals/route.ts`)
- **GET**: Returns both the `available_balance` (RPC) and list of user `withdrawals`.
- **POST**: Calls `request_withdrawal` RPC.
- **PATCH**: Soft-cancels `REQUESTED` withdrawals only if they belong to the user.

### Admin API (`auth-web/app/api/admin/withdrawals/route.ts`)
- **GET**: Fetches from `withdrawal_requests` and resolves user emails cleanly.
- **PATCH**: Supports setting statuses (`APPROVED`, `SENDING`, `COMPLETED`, `FAILED`, `REJECTED`), manages timestamps (e.g. `approved_at`, `failed_at`), and tracks `admin_id`. Doesn't call legacy commission functions.

## 4. Testing & Validation Status
- DB constraint guarantees preventing negative balance.
- Atomic SQL insertion completely stops Double Spend.
- Next.js route handlers configured with `force-dynamic` to avoid stale cache.
