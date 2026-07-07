CREATE TABLE IF NOT EXISTS uploaded_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID,
    user_id UUID,
    file_url TEXT NOT NULL,
    file_name TEXT,
    file_type TEXT,
    mime_type TEXT,
    duration FLOAT,
    width INTEGER,
    height INTEGER,
    aspect_ratio TEXT,
    file_size BIGINT,
    thumbnail_url TEXT,
    analysis_status TEXT DEFAULT 'pending',
    analysis_result JSONB,
    quality_score INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS asset_scene_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID,
    asset_id UUID REFERENCES uploaded_assets(id) ON DELETE CASCADE,
    scene_id UUID,
    shot_id UUID,
    match_score FLOAT,
    match_reason TEXT,
    confidence FLOAT,
    is_auto_matched BOOLEAN DEFAULT true,
    user_overridden BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_uploaded_assets_project_id ON uploaded_assets(project_id);
CREATE INDEX IF NOT EXISTS idx_asset_scene_matches_project_id ON asset_scene_matches(project_id);
CREATE INDEX IF NOT EXISTS idx_asset_scene_matches_shot_id ON asset_scene_matches(shot_id);
