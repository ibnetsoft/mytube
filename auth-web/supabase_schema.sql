-- =============================================================
-- PICADIRI STUDIO — Supabase Schema
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
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 신규 가입 시 profiles 자동 생성 트리거
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO public.profiles (id, email)
    VALUES (NEW.id, NEW.email)
    ON CONFLICT (id) DO NOTHING;
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
-- 4. RLS (Row Level Security) 정책
-- ─────────────────────────────────────────────

-- profiles: 본인 데이터만 읽기 / 관리자는 전체 읽기
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles_self_read" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "profiles_self_update" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- Service Role(어드민 백엔드)은 RLS bypass 가능 → 별도 정책 불필요

-- user_licenses: 본인 라이선스만 읽기 (쓰기는 서버 전용)
ALTER TABLE public.user_licenses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "licenses_self_read" ON public.user_licenses
    FOR SELECT USING (auth.uid() = user_id);

-- usage_logs: 본인 로그 읽기 (삽입은 서버 전용)
ALTER TABLE public.usage_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "logs_self_read" ON public.usage_logs
    FOR SELECT USING (auth.uid() = user_id);

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
