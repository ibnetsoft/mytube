-- =============================================================
-- Migration: Admin Treasury System (AIR-0201)
-- Description: Audit Logs, Commission, and Withdrawal RPCs
-- =============================================================

-- 1. Create Admin Audit Logs Table
CREATE TABLE IF NOT EXISTS public.admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_user_id UUID NOT NULL REFERENCES auth.users(id),
    action_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id UUID NOT NULL,
    previous_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for fast lookup by target or admin
CREATE INDEX IF NOT EXISTS idx_admin_audit_admin_id ON public.admin_audit_logs(admin_user_id);
CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON public.admin_audit_logs(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created_at ON public.admin_audit_logs(created_at);

-- RLS for audit logs
ALTER TABLE public.admin_audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Superadmins can view audit logs"
    ON public.admin_audit_logs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.is_superadmin = TRUE
        )
    );

-- 2. Utility for checking Superadmin inside RPCs
CREATE OR REPLACE FUNCTION public.is_admin(p_user_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    v_is_superadmin BOOLEAN;
BEGIN
    SELECT is_superadmin INTO v_is_superadmin
    FROM public.profiles
    WHERE id = p_user_id;
    RETURN COALESCE(v_is_superadmin, false);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- =============================================================
-- Commission Admin RPCs
-- =============================================================

-- Approve Commission
CREATE OR REPLACE FUNCTION admin_approve_commission(p_admin_id UUID, p_commission_id UUID, p_reason TEXT DEFAULT NULL)
RETURNS JSONB AS $$
DECLARE
    v_comm public.commissions;
BEGIN
    -- Security
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN
        RAISE EXCEPTION 'Unauthorized: Requires admin privileges';
    END IF;

    -- Lock and Load
    SELECT * INTO v_comm
    FROM public.commissions
    WHERE id = p_commission_id
    FOR UPDATE;

    IF v_comm.id IS NULL THEN
        RAISE EXCEPTION 'Commission not found';
    END IF;

    -- State check
    IF v_comm.status != 'PENDING' THEN
        RAISE EXCEPTION 'Invalid state transition: Commission is %', v_comm.status;
    END IF;

    -- Update
    UPDATE public.commissions
    SET status = 'APPROVED', updated_at = now()
    WHERE id = p_commission_id;

    -- Audit
    INSERT INTO public.admin_audit_logs (admin_user_id, action_type, target_type, target_id, previous_state, new_state, reason)
    VALUES (
        p_admin_id, 
        'APPROVE_COMMISSION', 
        'COMMISSION', 
        p_commission_id, 
        jsonb_build_object('status', v_comm.status), 
        jsonb_build_object('status', 'APPROVED'),
        p_reason
    );

    RETURN jsonb_build_object('success', true, 'id', p_commission_id, 'status', 'APPROVED');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Reject Commission
CREATE OR REPLACE FUNCTION admin_reject_commission(p_admin_id UUID, p_commission_id UUID, p_reason TEXT DEFAULT NULL)
RETURNS JSONB AS $$
DECLARE
    v_comm public.commissions;
BEGIN
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN
        RAISE EXCEPTION 'Unauthorized: Requires admin privileges';
    END IF;

    SELECT * INTO v_comm
    FROM public.commissions
    WHERE id = p_commission_id
    FOR UPDATE;

    IF v_comm.id IS NULL THEN RAISE EXCEPTION 'Commission not found'; END IF;
    IF v_comm.status != 'PENDING' THEN RAISE EXCEPTION 'Invalid state transition: Commission is %', v_comm.status; END IF;

    UPDATE public.commissions SET status = 'REJECTED', updated_at = now() WHERE id = p_commission_id;

    INSERT INTO public.admin_audit_logs (admin_user_id, action_type, target_type, target_id, previous_state, new_state, reason)
    VALUES (p_admin_id, 'REJECT_COMMISSION', 'COMMISSION', p_commission_id, jsonb_build_object('status', v_comm.status), jsonb_build_object('status', 'REJECTED'), p_reason);

    RETURN jsonb_build_object('success', true, 'id', p_commission_id, 'status', 'REJECTED');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- =============================================================
-- Withdrawal Admin RPCs
-- =============================================================

-- Approve Withdrawal
CREATE OR REPLACE FUNCTION admin_approve_withdrawal(p_admin_id UUID, p_withdrawal_id UUID, p_reason TEXT DEFAULT NULL)
RETURNS JSONB AS $$
DECLARE
    v_req public.withdrawal_requests;
BEGIN
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN RAISE EXCEPTION 'Unauthorized'; END IF;

    SELECT * INTO v_req FROM public.withdrawal_requests WHERE id = p_withdrawal_id FOR UPDATE;

    IF v_req.id IS NULL THEN RAISE EXCEPTION 'Withdrawal not found'; END IF;
    IF v_req.status != 'REQUESTED' THEN RAISE EXCEPTION 'Invalid state transition: %', v_req.status; END IF;

    UPDATE public.withdrawal_requests 
    SET status = 'APPROVED', approved_at = now(), approved_by = p_admin_id, updated_at = now() 
    WHERE id = p_withdrawal_id;

    INSERT INTO public.admin_audit_logs (admin_user_id, action_type, target_type, target_id, previous_state, new_state, reason)
    VALUES (p_admin_id, 'APPROVE_WITHDRAWAL', 'WITHDRAWAL', p_withdrawal_id, jsonb_build_object('status', v_req.status), jsonb_build_object('status', 'APPROVED'), p_reason);

    RETURN jsonb_build_object('success', true, 'id', p_withdrawal_id, 'status', 'APPROVED');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Reject Withdrawal
CREATE OR REPLACE FUNCTION admin_reject_withdrawal(p_admin_id UUID, p_withdrawal_id UUID, p_reason TEXT DEFAULT NULL)
RETURNS JSONB AS $$
DECLARE
    v_req public.withdrawal_requests;
BEGIN
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN RAISE EXCEPTION 'Unauthorized'; END IF;

    SELECT * INTO v_req FROM public.withdrawal_requests WHERE id = p_withdrawal_id FOR UPDATE;

    IF v_req.id IS NULL THEN RAISE EXCEPTION 'Withdrawal not found'; END IF;
    IF v_req.status != 'REQUESTED' THEN RAISE EXCEPTION 'Invalid state transition: %', v_req.status; END IF;

    UPDATE public.withdrawal_requests 
    SET status = 'REJECTED', rejected_at = now(), rejected_by = p_admin_id, admin_note = p_reason, updated_at = now() 
    WHERE id = p_withdrawal_id;

    INSERT INTO public.admin_audit_logs (admin_user_id, action_type, target_type, target_id, previous_state, new_state, reason)
    VALUES (p_admin_id, 'REJECT_WITHDRAWAL', 'WITHDRAWAL', p_withdrawal_id, jsonb_build_object('status', v_req.status), jsonb_build_object('status', 'REJECTED'), p_reason);

    RETURN jsonb_build_object('success', true, 'id', p_withdrawal_id, 'status', 'REJECTED');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Complete Withdrawal
CREATE OR REPLACE FUNCTION admin_complete_withdrawal(p_admin_id UUID, p_withdrawal_id UUID, p_tx_hash TEXT, p_reason TEXT DEFAULT NULL)
RETURNS JSONB AS $$
DECLARE
    v_req public.withdrawal_requests;
BEGIN
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN RAISE EXCEPTION 'Unauthorized'; END IF;

    SELECT * INTO v_req FROM public.withdrawal_requests WHERE id = p_withdrawal_id FOR UPDATE;

    IF v_req.id IS NULL THEN RAISE EXCEPTION 'Withdrawal not found'; END IF;
    IF v_req.status != 'APPROVED' THEN RAISE EXCEPTION 'Invalid state transition: Requires APPROVED, got %', v_req.status; END IF;
    
    IF p_tx_hash IS NULL OR p_tx_hash = '' THEN RAISE EXCEPTION 'tx_hash is required to complete withdrawal'; END IF;

    UPDATE public.withdrawal_requests 
    SET status = 'COMPLETED', completed_at = now(), tx_hash = p_tx_hash, updated_at = now() 
    WHERE id = p_withdrawal_id;

    INSERT INTO public.admin_audit_logs (admin_user_id, action_type, target_type, target_id, previous_state, new_state, reason)
    VALUES (p_admin_id, 'COMPLETE_WITHDRAWAL', 'WITHDRAWAL', p_withdrawal_id, jsonb_build_object('status', v_req.status), jsonb_build_object('status', 'COMPLETED', 'tx_hash', p_tx_hash), p_reason);

    RETURN jsonb_build_object('success', true, 'id', p_withdrawal_id, 'status', 'COMPLETED');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- =============================================================
-- Bulk Action Admin RPCs
-- =============================================================

CREATE OR REPLACE FUNCTION admin_bulk_approve_commissions(p_admin_id UUID, p_commission_ids UUID[])
RETURNS JSONB AS $$
DECLARE
    v_id UUID;
    v_count INT := 0;
BEGIN
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN RAISE EXCEPTION 'Unauthorized'; END IF;
    IF array_length(p_commission_ids, 1) > 100 THEN RAISE EXCEPTION 'Bulk action limit exceeded: Max 100 records'; END IF;

    FOREACH v_id IN ARRAY p_commission_ids
    LOOP
        -- Will raise exception if already approved or not found, causing whole transaction to rollback
        PERFORM admin_approve_commission(p_admin_id, v_id, 'Bulk Approval');
        v_count := v_count + 1;
    END LOOP;

    RETURN jsonb_build_object('success', true, 'approved_count', v_count);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION admin_bulk_approve_withdrawals(p_admin_id UUID, p_withdrawal_ids UUID[])
RETURNS JSONB AS $$
DECLARE
    v_id UUID;
    v_count INT := 0;
BEGIN
    IF NOT public.is_admin(p_admin_id) OR auth.uid() != p_admin_id THEN RAISE EXCEPTION 'Unauthorized'; END IF;
    IF array_length(p_withdrawal_ids, 1) > 100 THEN RAISE EXCEPTION 'Bulk action limit exceeded: Max 100 records'; END IF;

    FOREACH v_id IN ARRAY p_withdrawal_ids
    LOOP
        PERFORM admin_approve_withdrawal(p_admin_id, v_id, 'Bulk Approval');
        v_count := v_count + 1;
    END LOOP;

    RETURN jsonb_build_object('success', true, 'approved_count', v_count);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
