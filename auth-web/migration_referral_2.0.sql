-- 1. Insert default settings
INSERT INTO public.global_settings (key, value) VALUES
    ('referral_mode', 'NORMAL'),
    ('referral_default_sponsor_uuid', ''),
    ('referral_level1_percent', '10'),
    ('referral_level2_percent', '5'),
    ('referral_min_payout', '50'),
    ('referral_cycle', 'MONTHLY')
ON CONFLICT (key) DO NOTHING;

-- 2. Update existing users with NULL referred_by to the default sponsor (if set)
DO $$
DECLARE
    default_sponsor UUID;
BEGIN
    SELECT NULLIF(value, '')::UUID INTO default_sponsor
    FROM public.global_settings
    WHERE key = 'referral_default_sponsor_uuid';

    IF default_sponsor IS NOT NULL THEN
        UPDATE public.profiles
        SET referred_by = default_sponsor
        WHERE referred_by IS NULL
          AND id != default_sponsor;
    END IF;
EXCEPTION WHEN invalid_text_representation THEN
    -- In case the default sponsor UUID is not a valid UUID yet
    NULL;
END $$;
