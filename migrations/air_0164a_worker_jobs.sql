-- Migration: Create worker_jobs table (AIR-0164A)
-- Description: Generalized table to support flexible worker tasks for the Worker Job Center.

-- 1. Create Table
CREATE TABLE IF NOT EXISTS public.worker_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL, -- Nullable for unassigned jobs
    title TEXT NOT NULL,
    type VARCHAR(50) NOT NULL, -- e.g., Translation, Review, Classification
    priority VARCHAR(20) NOT NULL DEFAULT 'NORMAL', -- HIGH, NORMAL, LOW
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE', -- AVAILABLE, ACTIVE, COMPLETED, CANCELLED
    estimated_earnings NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    estimated_time VARCHAR(20), -- e.g., '5 mins', '10 mins'
    progress INT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT check_status_valid CHECK (status IN ('AVAILABLE', 'ACTIVE', 'COMPLETED', 'CANCELLED')),
    CONSTRAINT check_priority_valid CHECK (priority IN ('HIGH', 'NORMAL', 'LOW')),
    CONSTRAINT check_progress_range CHECK (progress >= 0 AND progress <= 100)
);

-- 2. Create Indexes
-- Performance indexes as requested by CTO
CREATE INDEX IF NOT EXISTS idx_worker_jobs_status ON public.worker_jobs(status);
CREATE INDEX IF NOT EXISTS idx_worker_jobs_user_id ON public.worker_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_worker_jobs_created_at ON public.worker_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_worker_jobs_completed_at ON public.worker_jobs(completed_at);

-- Composite indexes
CREATE INDEX IF NOT EXISTS idx_worker_jobs_status_created ON public.worker_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_worker_jobs_user_status_created ON public.worker_jobs(user_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_worker_jobs_user_completed ON public.worker_jobs(user_id, completed_at);

-- 3. Create updated_at trigger
CREATE OR REPLACE FUNCTION update_worker_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER set_worker_jobs_updated_at
    BEFORE UPDATE ON public.worker_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_worker_jobs_updated_at();

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.worker_jobs ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies

-- Policy 1: Users can view AVAILABLE jobs OR jobs assigned to them.
CREATE POLICY "Users can view available or their own jobs" 
    ON public.worker_jobs
    FOR SELECT
    USING (
        status = 'AVAILABLE' 
        OR user_id = auth.uid()
    );

-- Policy 2: Users can update a job to start it (if it's AVAILABLE and user_id is null)
-- OR update jobs they already own.
CREATE POLICY "Users can update available or their own jobs" 
    ON public.worker_jobs
    FOR UPDATE
    USING (
        (status = 'AVAILABLE' AND user_id IS NULL) 
        OR user_id = auth.uid()
    )
    WITH CHECK (
        user_id = auth.uid() -- They must claim it as themselves, or continue owning it
    );

-- Policy 3: Admins can do everything (Assuming service_role bypasses RLS, but if needed we can add an admin policy)
-- For now, relying on service_role for admin tasks is sufficient.

