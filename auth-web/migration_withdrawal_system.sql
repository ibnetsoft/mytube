-- =============================================================
-- Migration: Withdrawal System and USDT Balance
-- =============================================================

-- 1. Add usdt_balance and wallet_address to profiles table
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS usdt_balance NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';

-- 2. Create withdrawals table
CREATE TABLE IF NOT EXISTS public.withdrawals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    amount NUMERIC NOT NULL,
    dest_address TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'completed', 'rejected'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

-- 3. Create Indexes
CREATE INDEX IF NOT EXISTS idx_withdrawals_user_id ON public.withdrawals(user_id);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON public.withdrawals(status);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.withdrawals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "withdrawals_self_read" ON public.withdrawals;
DROP POLICY IF EXISTS "withdrawals_self_insert" ON public.withdrawals;

-- Policy: Users can read their own withdrawals
CREATE POLICY "withdrawals_self_read" ON public.withdrawals
    FOR SELECT USING (auth.uid() = user_id);

-- Policy: Users can insert their own withdrawals
CREATE POLICY "withdrawals_self_insert" ON public.withdrawals
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service Role (Admin backend) bypasses RLS, so it can read/update all withdrawals.
