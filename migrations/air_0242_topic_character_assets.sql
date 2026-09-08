-- AIR-0242: Topic-level character DNA and reference image registry.

CREATE TABLE IF NOT EXISTS public.topic_character_assets (
    id BIGSERIAL PRIMARY KEY,
    topic_queue_id BIGINT NOT NULL REFERENCES public.topics_queue(id) ON DELETE CASCADE,
    character_key TEXT NOT NULL,
    name TEXT,
    role TEXT,
    gender TEXT,
    age_group TEXT,
    category TEXT,
    script_style TEXT,
    image_style TEXT,
    story_style TEXT,
    visual_dna_en TEXT,
    wardrobe_en TEXT,
    continuity_instruction TEXT,
    prompt_en TEXT,
    image_prompt TEXT,
    image_url TEXT,
    storage_bucket TEXT NOT NULL DEFAULT 'content-assets',
    storage_object_path TEXT,
    dna JSONB NOT NULL DEFAULT '{}'::jsonb,
    usage_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    generation_model TEXT,
    generated_by_worker_id TEXT,
    source TEXT NOT NULL DEFAULT 'hermes_worker',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (topic_queue_id, character_key)
);

CREATE INDEX IF NOT EXISTS idx_topic_character_assets_topic_queue_id
    ON public.topic_character_assets(topic_queue_id);

CREATE INDEX IF NOT EXISTS idx_topic_character_assets_category_style
    ON public.topic_character_assets(category, script_style, image_style);

ALTER TABLE public.topic_character_assets ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.topic_character_assets TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.topic_character_assets_id_seq TO service_role;
