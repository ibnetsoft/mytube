-- =============================================================
-- Migration: Create withdrawal_requests table (AIR-0158D)
-- Description: New Ledger for handling withdrawals separating logic from commissions.
-- =============================================================

-- 1. Create Table
CREATE TABLE IF NOT EXISTS public.withdrawal_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    amount NUMERIC(18,6) NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'USDT' CHECK (currency = 'USDT'),
    network TEXT NOT NULL DEFAULT 'BEP20' CHECK (network = 'BEP20'),
    wallet_address TEXT NOT NULL CHECK (wallet_address ~ '^0x[a-fA-F0-9]{40}$'),
    status TEXT NOT NULL DEFAULT 'REQUESTED' 
        CHECK (status IN ('REQUESTED', 'APPROVED', 'SENDING', 'COMPLETED', 'FAILED', 'REJECTED', 'CANCELED')),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    tx_hash TEXT,
    failure_reason TEXT,
    admin_note TEXT,
    approved_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    rejected_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Create Indexes
CREATE INDEX IF NOT EXISTS idx_withdrawal_reqs_user_id ON public.withdrawal_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_withdrawal_reqs_status ON public.withdrawal_requests(status);
CREATE INDEX IF NOT EXISTS idx_withdrawal_reqs_created_at ON public.withdrawal_requests(created_at);

-- 3. Trigger for updated_at
CREATE OR REPLACE FUNCTION update_withdrawal_requests_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_withdrawal_reqs_updated_at ON public.withdrawal_requests;
CREATE TRIGGER set_withdrawal_reqs_updated_at
    BEFORE UPDATE ON public.withdrawal_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_withdrawal_requests_updated_at();

-- 4. Enable RLS
ALTER TABLE public.withdrawal_requests ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies
-- 5a. Users can read their own withdrawal requests
CREATE POLICY "Users can view own withdrawal requests" 
    ON public.withdrawal_requests 
    FOR SELECT 
    USING (auth.uid() = user_id);

-- 5b. Users can insert their own withdrawal requests (Must be 'REQUESTED')
CREATE POLICY "Users can insert own withdrawal requests" 
    ON public.withdrawal_requests 
    FOR INSERT 
    WITH CHECK (auth.uid() = user_id AND status = 'REQUESTED');

-- 5c. Users can cancel their own pending withdrawal requests
CREATE POLICY "Users can cancel own pending withdrawal requests" 
    ON public.withdrawal_requests 
    FOR UPDATE 
    USING (auth.uid() = user_id AND status = 'REQUESTED')
    WITH CHECK (status = 'CANCELED');

-- 5d. Admins can view all (assuming is_superadmin logic or app-level bypass for service role)
-- Service Role bypasses RLS by default. If we need explicit admin policy using is_superadmin:
CREATE POLICY "Admins can view all withdrawal requests" 
    ON public.withdrawal_requests 
    FOR SELECT 
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );

CREATE POLICY "Admins can update all withdrawal requests" 
    ON public.withdrawal_requests 
    FOR UPDATE 
    USING (
        EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );
