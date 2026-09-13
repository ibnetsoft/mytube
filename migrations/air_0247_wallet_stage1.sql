-- AIR-0247: Stage 1 centralized wallet foundation
--
-- Scope:
-- - Real ERC20 wallet address/private key per user.
-- - AIR deposits detected from chain events.
-- - Internal AIR/USDT balances and immutable ledger rows.
-- - Internal AIR<->USDT swaps.
-- - External send/withdrawal requests:
--   * AIR: ERC20 address.
--   * USDT: BEP20 address only. Actual USDT transfer is handled manually by admin.
--
-- Security model for Stage 1:
-- - Application/admin APIs use the service-role key.
-- - End users must not query these tables directly, especially wallet_accounts
--   because Stage 1 stores the private key in the DB as requested.
-- - RLS is enabled on every table; no client-facing policies are added here.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallet_asset') THEN
        CREATE TYPE public.wallet_asset AS ENUM ('AIR', 'USDT');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallet_ledger_direction') THEN
        CREATE TYPE public.wallet_ledger_direction AS ENUM ('credit', 'debit');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallet_ledger_reason') THEN
        CREATE TYPE public.wallet_ledger_reason AS ENUM (
            'wallet_created',
            'air_deposit',
            'swap',
            'swap_fee',
            'withdrawal_request',
            'withdrawal_fee',
            'withdrawal_reject_refund',
            'admin_adjustment'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallet_deposit_status') THEN
        CREATE TYPE public.wallet_deposit_status AS ENUM ('PENDING', 'CONFIRMED', 'IGNORED', 'FAILED');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallet_swap_status') THEN
        CREATE TYPE public.wallet_swap_status AS ENUM ('COMPLETED', 'FAILED', 'CANCELED');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallet_withdrawal_status') THEN
        CREATE TYPE public.wallet_withdrawal_status AS ENUM (
            'REQUESTED',
            'APPROVED',
            'SENDING',
            'COMPLETED',
            'REJECTED',
            'FAILED',
            'CANCELED'
        );
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.air_wallet_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS public.wallet_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    chain_id INTEGER NOT NULL DEFAULT 1,
    address TEXT NOT NULL CHECK (address ~ '^0x[a-fA-F0-9]{40}$'),
    private_key TEXT NOT NULL,
    key_storage_mode TEXT NOT NULL DEFAULT 'plain_db' CHECK (key_storage_mode IN ('plain_db', 'encrypted_db', 'external_kms')),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED', 'DISABLED')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_wallet_accounts_address_lower
    ON public.wallet_accounts (lower(address));

DROP TRIGGER IF EXISTS trg_wallet_accounts_updated_at ON public.wallet_accounts;
CREATE TRIGGER trg_wallet_accounts_updated_at
    BEFORE UPDATE ON public.wallet_accounts
    FOR EACH ROW
    EXECUTE FUNCTION public.air_wallet_set_updated_at();

CREATE TABLE IF NOT EXISTS public.wallet_balances (
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    asset public.wallet_asset NOT NULL,
    available_amount NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (available_amount >= 0),
    locked_amount NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (locked_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, asset)
);

DROP TRIGGER IF EXISTS trg_wallet_balances_updated_at ON public.wallet_balances;
CREATE TRIGGER trg_wallet_balances_updated_at
    BEFORE UPDATE ON public.wallet_balances
    FOR EACH ROW
    EXECUTE FUNCTION public.air_wallet_set_updated_at();

CREATE TABLE IF NOT EXISTS public.wallet_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    asset public.wallet_asset NOT NULL,
    direction public.wallet_ledger_direction NOT NULL,
    amount NUMERIC(36, 18) NOT NULL CHECK (amount > 0),
    available_after NUMERIC(36, 18),
    locked_after NUMERIC(36, 18),
    reason public.wallet_ledger_reason NOT NULL,
    reference_type TEXT,
    reference_id UUID,
    idempotency_key TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_asset_created
    ON public.wallet_ledger (user_id, asset, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_reference
    ON public.wallet_ledger (reference_type, reference_id);

CREATE TABLE IF NOT EXISTS public.air_deposits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    wallet_account_id UUID REFERENCES public.wallet_accounts(id) ON DELETE SET NULL,
    chain_id INTEGER NOT NULL DEFAULT 1,
    air_contract_address TEXT NOT NULL CHECK (air_contract_address ~ '^0x[a-fA-F0-9]{40}$'),
    tx_hash TEXT NOT NULL CHECK (tx_hash ~ '^0x[a-fA-F0-9]{64}$'),
    log_index INTEGER NOT NULL CHECK (log_index >= 0),
    block_number NUMERIC(30, 0),
    from_address TEXT CHECK (from_address IS NULL OR from_address ~ '^0x[a-fA-F0-9]{40}$'),
    to_address TEXT NOT NULL CHECK (to_address ~ '^0x[a-fA-F0-9]{40}$'),
    amount NUMERIC(36, 18) NOT NULL CHECK (amount > 0),
    confirmations INTEGER NOT NULL DEFAULT 0 CHECK (confirmations >= 0),
    status public.wallet_deposit_status NOT NULL DEFAULT 'PENDING',
    credited_ledger_id UUID REFERENCES public.wallet_ledger(id) ON DELETE SET NULL,
    raw_event JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chain_id, tx_hash, log_index)
);

CREATE INDEX IF NOT EXISTS idx_air_deposits_user_created
    ON public.air_deposits (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_air_deposits_status_block
    ON public.air_deposits (status, block_number);
CREATE INDEX IF NOT EXISTS idx_air_deposits_to_address_lower
    ON public.air_deposits (lower(to_address));

DROP TRIGGER IF EXISTS trg_air_deposits_updated_at ON public.air_deposits;
CREATE TRIGGER trg_air_deposits_updated_at
    BEFORE UPDATE ON public.air_deposits
    FOR EACH ROW
    EXECUTE FUNCTION public.air_wallet_set_updated_at();

CREATE TABLE IF NOT EXISTS public.wallet_swaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    from_asset public.wallet_asset NOT NULL,
    to_asset public.wallet_asset NOT NULL,
    from_amount NUMERIC(36, 18) NOT NULL CHECK (from_amount > 0),
    gross_to_amount NUMERIC(36, 18) NOT NULL CHECK (gross_to_amount >= 0),
    fee_asset public.wallet_asset NOT NULL,
    fee_amount NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
    net_to_amount NUMERIC(36, 18) NOT NULL CHECK (net_to_amount >= 0),
    rate NUMERIC(36, 18) NOT NULL CHECK (rate > 0),
    status public.wallet_swap_status NOT NULL DEFAULT 'COMPLETED',
    request_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CHECK (from_asset <> to_asset)
);

CREATE INDEX IF NOT EXISTS idx_wallet_swaps_user_created
    ON public.wallet_swaps (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.wallet_withdrawal_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    asset public.wallet_asset NOT NULL,
    network TEXT NOT NULL,
    to_address TEXT NOT NULL CHECK (to_address ~ '^0x[a-fA-F0-9]{40}$'),
    requested_amount NUMERIC(36, 18) NOT NULL CHECK (requested_amount > 0),
    fee_amount NUMERIC(36, 18) NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
    net_amount NUMERIC(36, 18) NOT NULL CHECK (net_amount > 0),
    status public.wallet_withdrawal_status NOT NULL DEFAULT 'REQUESTED',
    tx_hash TEXT CHECK (tx_hash IS NULL OR tx_hash ~ '^0x[a-fA-F0-9]{64}$'),
    admin_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    admin_memo TEXT,
    failure_reason TEXT,
    request_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    canceled_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (asset = 'USDT'::public.wallet_asset AND network = 'BEP20')
        OR
        (asset = 'AIR'::public.wallet_asset AND network = 'ERC20')
    )
);

CREATE INDEX IF NOT EXISTS idx_wallet_withdrawal_requests_user_created
    ON public.wallet_withdrawal_requests (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_withdrawal_requests_status_created
    ON public.wallet_withdrawal_requests (status, created_at DESC);

DROP TRIGGER IF EXISTS trg_wallet_withdrawal_requests_updated_at ON public.wallet_withdrawal_requests;
CREATE TRIGGER trg_wallet_withdrawal_requests_updated_at
    BEFORE UPDATE ON public.wallet_withdrawal_requests
    FOR EACH ROW
    EXECUTE FUNCTION public.air_wallet_set_updated_at();

CREATE TABLE IF NOT EXISTS public.wallet_admin_settings_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    setting_source TEXT NOT NULL DEFAULT 'global_settings',
    settings JSONB NOT NULL,
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wallet_admin_settings_snapshots_created
    ON public.wallet_admin_settings_snapshots (created_at DESC);

ALTER TABLE public.wallet_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_balances ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.air_deposits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_swaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_withdrawal_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_admin_settings_snapshots ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.wallet_accounts IS
    'Stage 1 centralized wallet accounts. Contains DB-stored private keys; access only through server/service-role APIs.';
COMMENT ON COLUMN public.wallet_accounts.private_key IS
    'Stage 1 stores the raw private key in DB by explicit product decision. Move to encryption/KMS/MPC in Stage 2.';
COMMENT ON TABLE public.wallet_balances IS
    'Internal source-of-truth balances for AIR and USDT.';
COMMENT ON TABLE public.wallet_ledger IS
    'Immutable wallet balance movement audit trail.';
COMMENT ON TABLE public.air_deposits IS
    'AIR ERC20 Transfer events credited to user wallets. Unique tx_hash/log_index prevents duplicate credits.';
COMMENT ON TABLE public.wallet_swaps IS
    'Internal AIR/USDT swap transactions using admin-configured rates and fees.';
COMMENT ON TABLE public.wallet_withdrawal_requests IS
    'User external send/withdrawal requests. USDT is BEP20 only and manually paid by admin in Stage 1.';
