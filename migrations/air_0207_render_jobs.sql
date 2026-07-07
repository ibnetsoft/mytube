-- migrations/air_0207_render_jobs.sql

CREATE TABLE IF NOT EXISTS render_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id INTEGER,
    production_item_id VARCHAR(255) NOT NULL,
    shot_id VARCHAR(255) NOT NULL,
    scene_id VARCHAR(255) NOT NULL,
    asset_type VARCHAR(50) NOT NULL CHECK (asset_type IN ('image', 'video', 'reuse')),
    generator VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'retry')),
    priority VARCHAR(50) DEFAULT 'normal',
    input_payload JSONB,
    output_payload JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    locked_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);

-- Indexes for efficient queue pulling and filtering
CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON render_jobs (status);
CREATE INDEX IF NOT EXISTS idx_render_jobs_generator ON render_jobs (generator);
CREATE INDEX IF NOT EXISTS idx_render_jobs_asset_type ON render_jobs (asset_type);
CREATE INDEX IF NOT EXISTS idx_render_jobs_created_at ON render_jobs (created_at);
