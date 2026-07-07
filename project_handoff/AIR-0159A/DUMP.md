# AIR-0159A Handoff Dump

Implemented User Withdrawal Dashboard UI.
- Path: `/dashboard/withdrawals`
- API used: `/api/user/withdrawals` (GET, POST, PATCH)
- Implemented features: Check available balance, request withdrawal (USDT/BEP20 fixed), view history list, cancel `REQUESTED` withdrawals.
- Replaced legacy balance calculation with the new withdrawal ledger API.
