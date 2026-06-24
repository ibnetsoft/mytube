-- =============================================================
-- AIR STUDIO — Supabase Schema
-- Supabase 대시보드 > SQL Editor 에서 순서대로 실행하세요.
-- =============================================================

-- ─────────────────────────────────────────────
-- 1. profiles: auth.users 와 1:1 연동되는 공개 프로필
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT,
    membership_tier TEXT NOT NULL DEFAULT 'standard',   -- 'standard' | 'pro' | 'admin'
    video_limit     INT  NOT NULL DEFAULT 50,           -- 월 생성 가능 영상 수
    current_usage   INT  NOT NULL DEFAULT 0,            -- 이번 달 사용량
    usage_reset_at  TIMESTAMPTZ DEFAULT date_trunc('month', NOW()) + INTERVAL '1 month',
    preferred_languages TEXT[] DEFAULT ARRAY['ko'::text],
    referral_code   TEXT UNIQUE,
    referred_by     UUID REFERENCES public.profiles(id),
    referral_depth  INT DEFAULT 0,
    country_code    TEXT DEFAULT 'KR',
    referral_country TEXT,
    commission_rate NUMERIC(5,2) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 신규 가입 시 profiles 자동 생성 트리거
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    raw_preferred_languages TEXT[];
    clean_preferred_languages TEXT[];
    raw_referral_code TEXT;
    generated_referral_code TEXT;
    referrer_profile public.profiles%ROWTYPE;
    normalized_country TEXT;
BEGIN
    SELECT ARRAY(
        SELECT DISTINCT lang
        FROM jsonb_array_elements_text(COALESCE(NEW.raw_user_meta_data->'preferred_languages', '["ko"]'::jsonb)) AS lang
        WHERE lang IN ('ko', 'en', 'ja')
    ) INTO raw_preferred_languages;

    clean_preferred_languages := COALESCE(NULLIF(raw_preferred_languages, ARRAY[]::TEXT[]), ARRAY['ko'::TEXT]);
    raw_referral_code := upper(trim(COALESCE(NEW.raw_user_meta_data->>'referral_code', NEW.raw_user_meta_data->>'referrer', '')));
    normalized_country := upper(left(regexp_replace(COALESCE(NEW.raw_user_meta_data->>'country_code', NEW.raw_user_meta_data->>'nationality', 'KR'), '[^A-Za-z]', '', 'g'), 2));
    IF normalized_country = '' THEN
        normalized_country := 'KR';
    END IF;

    IF raw_referral_code <> '' THEN
        SELECT * INTO referrer_profile
        FROM public.profiles
        WHERE upper(referral_code) = raw_referral_code
        LIMIT 1;
    END IF;

    LOOP
        generated_referral_code := upper(substr(md5(random()::text || clock_timestamp()::text || NEW.id::text), 1, 8));
        EXIT WHEN NOT EXISTS (SELECT 1 FROM public.profiles WHERE referral_code = generated_referral_code);
    END LOOP;

    INSERT INTO public.profiles (
        id, email, preferred_languages, referral_code, referred_by,
        referral_depth, country_code, referral_country, commission_rate
    )
    VALUES (
        NEW.id,
        NEW.email,
        clean_preferred_languages,
        generated_referral_code,
        referrer_profile.id,
        COALESCE(referrer_profile.referral_depth + 1, 0),
        normalized_country,
        COALESCE(referrer_profile.referral_country, referrer_profile.country_code, normalized_country),
        0
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        preferred_languages = COALESCE(public.profiles.preferred_languages, EXCLUDED.preferred_languages),
        referral_code = COALESCE(public.profiles.referral_code, EXCLUDED.referral_code),
        referred_by = COALESCE(public.profiles.referred_by, EXCLUDED.referred_by),
        referral_depth = COALESCE(public.profiles.referral_depth, EXCLUDED.referral_depth),
        country_code = COALESCE(public.profiles.country_code, EXCLUDED.country_code),
        referral_country = COALESCE(public.profiles.referral_country, EXCLUDED.referral_country),
        commission_rate = COALESCE(public.profiles.commission_rate, EXCLUDED.commission_rate);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ─────────────────────────────────────────────
-- 2. user_licenses: 로컬 앱 라이선스 키 ↔ Supabase 계정 매핑
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_licenses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    license_key   TEXT NOT NULL UNIQUE,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    activated_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at    TIMESTAMPTZ,                          -- NULL = 무기한
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_licenses_key ON public.user_licenses(license_key);
CREATE INDEX IF NOT EXISTS idx_user_licenses_user ON public.user_licenses(user_id);

-- ─────────────────────────────────────────────
-- 3. usage_logs: 기능별 사용량 추적
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.usage_logs (
    id           BIGSERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    feature      TEXT NOT NULL,  -- 'video_render' | 'tts' | 'image_gen' | 'autopilot' 등
    project_id   TEXT,
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_user ON public.usage_logs(user_id, created_at DESC);

-- ─────────────────────────────────────────────
-- 3-1. referral_commissions: 추천인 커미션 적립/정산 이력
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.referral_commissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    beneficiary_id  UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    source_user_id  UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    commission_type TEXT NOT NULL DEFAULT 'direct', -- direct | level2 | country | payout
    base_tokens     BIGINT NOT NULL DEFAULT 0,
    rate_percent    NUMERIC(5,2) NOT NULL DEFAULT 0,
    commission_tokens BIGINT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending', -- pending | paid | cancelled
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    paid_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_referral_commissions_beneficiary ON public.referral_commissions(beneficiary_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_referral_commissions_status ON public.referral_commissions(status, created_at DESC);

-- ─────────────────────────────────────────────
-- desktop_project_metadata: 로컬 앱 프로젝트 텍스트/메타데이터 동기화
-- 이미지/영상/음성 파일 자체는 로컬에 유지하고, JSON payload에는 텍스트/상태/요약만 저장합니다.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.desktop_project_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_id TEXT NOT NULL UNIQUE,
    user_id UUID NULL REFERENCES auth.users(id) ON DELETE SET NULL,
    employee_email TEXT,
    local_project_id BIGINT,
    name TEXT,
    topic TEXT,
    status TEXT,
    language TEXT,
    app_mode TEXT,
    project_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_desktop_project_metadata_email
ON public.desktop_project_metadata(employee_email);

CREATE INDEX IF NOT EXISTS idx_desktop_project_metadata_local_project
ON public.desktop_project_metadata(employee_email, local_project_id);

ALTER TABLE public.desktop_project_metadata ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "desktop_project_metadata_self_read" ON public.desktop_project_metadata;
CREATE POLICY "desktop_project_metadata_self_read" ON public.desktop_project_metadata
    FOR SELECT USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- project_learning_events / snapshots: 로컬 앱 제작 학습 데이터 중앙 저장
-- 로컬 앱에서 service role로 적재하고, 웹어드민은 집계/조회에 사용합니다.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.project_learning_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_key TEXT NOT NULL UNIQUE,
    local_event_id BIGINT NOT NULL,
    local_project_id BIGINT NOT NULL,
    project_sync_id TEXT,
    user_id UUID NULL REFERENCES auth.users(id) ON DELETE SET NULL,
    employee_email TEXT,
    project_name TEXT,
    project_topic TEXT,
    event_type TEXT NOT NULL,
    stage TEXT,
    source TEXT DEFAULT 'system',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    local_created_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_learning_events_user_created
ON public.project_learning_events(user_id, local_created_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_learning_events_type_stage
ON public.project_learning_events(event_type, stage);

CREATE INDEX IF NOT EXISTS idx_project_learning_events_project
ON public.project_learning_events(project_sync_id, local_project_id);

CREATE TABLE IF NOT EXISTS public.project_learning_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_key TEXT NOT NULL UNIQUE,
    local_snapshot_id BIGINT NOT NULL,
    local_project_id BIGINT NOT NULL,
    project_sync_id TEXT,
    user_id UUID NULL REFERENCES auth.users(id) ON DELETE SET NULL,
    employee_email TEXT,
    project_name TEXT,
    project_topic TEXT,
    snapshot_type TEXT NOT NULL,
    reference JSONB NOT NULL DEFAULT '{}'::jsonb,
    style JSONB NOT NULL DEFAULT '{}'::jsonb,
    script JSONB NOT NULL DEFAULT '{}'::jsonb,
    thumbnail JSONB NOT NULL DEFAULT '{}'::jsonb,
    tts JSONB NOT NULL DEFAULT '{}'::jsonb,
    video JSONB NOT NULL DEFAULT '{}'::jsonb,
    qa JSONB NOT NULL DEFAULT '{}'::jsonb,
    upload JSONB NOT NULL DEFAULT '{}'::jsonb,
    local_created_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_learning_snapshots_user_created
ON public.project_learning_snapshots(user_id, local_created_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_learning_snapshots_project_type
ON public.project_learning_snapshots(project_sync_id, local_project_id, snapshot_type);

ALTER TABLE public.project_learning_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_learning_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "project_learning_events_self_read" ON public.project_learning_events;
CREATE POLICY "project_learning_events_self_read" ON public.project_learning_events
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "project_learning_snapshots_self_read" ON public.project_learning_snapshots;
CREATE POLICY "project_learning_snapshots_self_read" ON public.project_learning_snapshots
    FOR SELECT USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────
-- topic assignment style columns: 웹어드민 주제배정 대기열 스타일 표시/재배정
-- 기존 테이블에 안전하게 컬럼만 추가합니다.
-- ─────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'categories'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'categories' AND column_name = 'default_script_style'
        ) THEN
            ALTER TABLE public.categories ADD COLUMN default_script_style TEXT DEFAULT 'default';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'categories' AND column_name = 'default_image_style'
        ) THEN
            ALTER TABLE public.categories ADD COLUMN default_image_style TEXT DEFAULT 'realistic';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'categories' AND column_name = 'language'
        ) THEN
            ALTER TABLE public.categories ADD COLUMN language VARCHAR(5) DEFAULT 'ko';
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'topics_queue'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'topics_queue' AND column_name = 'assigned_script_style'
        ) THEN
            ALTER TABLE public.topics_queue ADD COLUMN assigned_script_style TEXT DEFAULT 'default';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'topics_queue' AND column_name = 'assigned_image_style'
        ) THEN
            ALTER TABLE public.topics_queue ADD COLUMN assigned_image_style TEXT DEFAULT 'realistic';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'topics_queue' AND column_name = 'language'
        ) THEN
            ALTER TABLE public.topics_queue ADD COLUMN language VARCHAR(5) DEFAULT 'ko';
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'profiles'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'preferred_languages'
        ) THEN
            ALTER TABLE public.profiles ADD COLUMN preferred_languages TEXT[] DEFAULT ARRAY['ko'::text];
        END IF;

        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'referral_code') THEN
            ALTER TABLE public.profiles ADD COLUMN referral_code TEXT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'referred_by') THEN
            ALTER TABLE public.profiles ADD COLUMN referred_by UUID REFERENCES public.profiles(id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'referral_depth') THEN
            ALTER TABLE public.profiles ADD COLUMN referral_depth INT DEFAULT 0;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'country_code') THEN
            ALTER TABLE public.profiles ADD COLUMN country_code TEXT DEFAULT 'KR';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'referral_country') THEN
            ALTER TABLE public.profiles ADD COLUMN referral_country TEXT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'commission_rate') THEN
            ALTER TABLE public.profiles ADD COLUMN commission_rate NUMERIC(5,2) DEFAULT 0;
        END IF;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'profiles_referral_code_unique') THEN
        CREATE UNIQUE INDEX profiles_referral_code_unique ON public.profiles(referral_code) WHERE referral_code IS NOT NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_profiles_referred_by') THEN
        CREATE INDEX idx_profiles_referred_by ON public.profiles(referred_by);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_profiles_referral_country') THEN
        CREATE INDEX idx_profiles_referral_country ON public.profiles(referral_country);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'categories_language_check') THEN
        ALTER TABLE public.categories ADD CONSTRAINT categories_language_check CHECK (language IN ('ko', 'en', 'ja'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'topics_queue_language_check') THEN
        ALTER TABLE public.topics_queue ADD CONSTRAINT topics_queue_language_check CHECK (language IN ('ko', 'en', 'ja'));
    END IF;
END $$;

-- ─────────────────────────────────────────────
-- 4. RLS (Row Level Security) 정책
-- ─────────────────────────────────────────────

-- profiles: 본인 데이터만 읽기 / 관리자는 전체 읽기
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "profiles_self_read" ON public.profiles;
CREATE POLICY "profiles_self_read" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "profiles_self_update" ON public.profiles;
CREATE POLICY "profiles_self_update" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- Service Role(어드민 백엔드)은 RLS bypass 가능 → 별도 정책 불필요

-- user_licenses: 본인 라이선스만 읽기 (쓰기는 서버 전용)
ALTER TABLE public.user_licenses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "licenses_self_read" ON public.user_licenses;
CREATE POLICY "licenses_self_read" ON public.user_licenses
    FOR SELECT USING (auth.uid() = user_id);

-- usage_logs: 본인 로그 읽기 (삽입은 서버 전용)
ALTER TABLE public.usage_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "logs_self_read" ON public.usage_logs;
CREATE POLICY "logs_self_read" ON public.usage_logs
    FOR SELECT USING (auth.uid() = user_id);

ALTER TABLE public.referral_commissions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "referral_commissions_self_read" ON public.referral_commissions;
CREATE POLICY "referral_commissions_self_read" ON public.referral_commissions
    FOR SELECT USING (auth.uid() = beneficiary_id);

-- ─────────────────────────────────────────────
-- 5. 라이선스 키 검증 함수 (로컬 앱에서 호출)
--    입력: license_key TEXT
--    반환: { user_id, membership_tier, video_limit, current_usage, is_active }
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.verify_license(p_license_key TEXT)
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_license  public.user_licenses%ROWTYPE;
    v_profile  public.profiles%ROWTYPE;
BEGIN
    SELECT * INTO v_license
    FROM public.user_licenses
    WHERE license_key = p_license_key AND is_active = TRUE
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN json_build_object('valid', FALSE, 'reason', 'invalid_key');
    END IF;

    IF v_license.expires_at IS NOT NULL AND v_license.expires_at < NOW() THEN
        RETURN json_build_object('valid', FALSE, 'reason', 'expired');
    END IF;

    SELECT * INTO v_profile FROM public.profiles WHERE id = v_license.user_id;

    RETURN json_build_object(
        'valid',          TRUE,
        'user_id',        v_license.user_id,
        'membership_tier', v_profile.membership_tier,
        'video_limit',    v_profile.video_limit,
        'current_usage',  v_profile.current_usage
    );
END;
$$;

-- ─────────────────────────────────────────────
-- 6. 사용량 증가 함수 (영상 1개 생성 완료 시 호출)
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.increment_usage(p_user_id UUID, p_feature TEXT DEFAULT 'video_render')
RETURNS JSON LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_profile public.profiles%ROWTYPE;
BEGIN
    SELECT * INTO v_profile FROM public.profiles WHERE id = p_user_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', FALSE, 'reason', 'user_not_found');
    END IF;

    -- 월 초기화 체크
    IF NOW() >= v_profile.usage_reset_at THEN
        UPDATE public.profiles
        SET current_usage  = 0,
            usage_reset_at = date_trunc('month', NOW()) + INTERVAL '1 month',
            updated_at     = NOW()
        WHERE id = p_user_id;
        v_profile.current_usage := 0;
    END IF;

    -- 한도 체크
    IF v_profile.current_usage >= v_profile.video_limit THEN
        RETURN json_build_object('success', FALSE, 'reason', 'quota_exceeded',
            'current_usage', v_profile.current_usage,
            'video_limit',   v_profile.video_limit);
    END IF;

    -- 사용량 증가
    UPDATE public.profiles
    SET current_usage = current_usage + 1, updated_at = NOW()
    WHERE id = p_user_id;

    -- 로그 기록
    INSERT INTO public.usage_logs (user_id, feature)
    VALUES (p_user_id, p_feature);

    RETURN json_build_object('success', TRUE,
        'current_usage', v_profile.current_usage + 1,
        'video_limit',   v_profile.video_limit);
END;
$$;

-- ─────────────────────────────────────────────
-- 7. global_settings: 시스템 전역 설정 및 API 키 저장용 테이블
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.global_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- 8. remote_render_queue: 원격 비디오 렌더링 순차 큐 및 진행 정보 관리용 테이블
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.remote_render_queue (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   INTEGER NOT NULL,
    project_name TEXT,
    email        TEXT,
    status       TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'rendering' | 'completed' | 'failed'
    progress     INTEGER DEFAULT 0,
    message      TEXT,
    render_mode  TEXT DEFAULT 'http_zip',
    asset_file_id TEXT,
    asset_file_name TEXT,
    result_file_id TEXT,
    result_file_name TEXT,
    worker_id    TEXT,
    claimed_at   TIMESTAMPTZ,
    error_message TEXT,
    retry_count  INTEGER DEFAULT 0,
    metadata     JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
