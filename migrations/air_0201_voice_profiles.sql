-- Migration for AIR-0201: Voice Intelligence System Phase 1
-- Create voice_profiles table

CREATE TABLE IF NOT EXISTS public.voice_profiles (
    id uuid primary key default gen_random_uuid(),
    provider text not null default 'elevenlabs',
    provider_voice_id text not null,
    voice_name text not null,
    
    language text not null,
    gender text null,
    age_group text null,
    
    tone text null,
    pitch text null,
    speed text null,
    energy text null,
    warmth int null,
    clarity int null,
    emotion_range int null,
    
    recommended_genres jsonb null,
    avoid_genres jsonb null,
    
    sample_audio_url text null,
    sample_duration numeric null,
    sample_language text null,
    sample_hash text null,
    description text null,
    
    analysis_status text not null default 'pending' CHECK (analysis_status IN ('pending', 'analyzing', 'manual', 'analyzed', 'failed', 'needs_review')),
    analysis_result jsonb null,
    voice_traits jsonb null,
    
    is_active boolean not null default true,
    
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Add unique constraint on provider and provider_voice_id
ALTER TABLE public.voice_profiles ADD CONSTRAINT uq_voice_profiles_provider_voice_id UNIQUE (provider, provider_voice_id);

-- Add RLS Policies
ALTER TABLE public.voice_profiles ENABLE ROW LEVEL SECURITY;

-- Allow read access for everyone
CREATE POLICY "Allow public read access to voice_profiles" ON public.voice_profiles FOR SELECT USING (true);

-- Allow all access for superadmin
CREATE POLICY "Allow all access to voice_profiles for superadmin" ON public.voice_profiles FOR ALL USING (
    auth.uid() IN (
        SELECT id FROM public.profiles WHERE is_superadmin = true
    )
);
