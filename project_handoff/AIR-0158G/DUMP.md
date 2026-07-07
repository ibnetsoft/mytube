# AIR-0158G Handoff Dump

HOTFIX complete. Added `SELECT ... FOR UPDATE` lock in `public.request_withdrawal` to strictly serialize withdrawal requests from the same user, preventing Double Spend attacks completely.
